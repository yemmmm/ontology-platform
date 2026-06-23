from app.mcp.server import mcp


def test_ontology_builder_mcp_surface_is_complete_and_excludes_human_actions() -> None:
    names = {tool.name for tool in mcp._tool_manager.list_tools()}

    assert {
        "get_build_context",
        "get_project_brief",
        "update_project_brief",
        "list_competency_questions",
        "propose_competency_questions",
        "list_source_documents",
        "get_source_document_status",
        "propose_schema_changes",
        "propose_entities",
        "propose_relations",
        "propose_entity_merges",
        "validate_draft",
        "list_review_items",
        "get_review_batch",
        "get_review_workspace_link",
        "get_publication_readiness",
    } <= names
    assert {
        "approve_proposal",
        "apply_approved_proposal",
        "review_fact_claim",
        "resolve_conflict",
        "publish_version",
        "deprecate_version",
    }.isdisjoint(names)
