import asyncio
from types import SimpleNamespace

import pytest

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.mcp.server import mcp
from app.mcp.tools import register_all
from app.repositories.models import OntologyModel, ProjectModel
from app.services.modeling_handlers import ModelingCommandHandlerRegistry


# Stage 3 B2 hard-cut: the only surviving MCP tool families are
# - system (platform health probe)
# - interview (brief, competency-questions CRUD — Stage 1 disposition K)
# - semantic (the new RDF/graph-set stack)
ALLOWED_TOOLS = {
    "submit_semantic_feedback",
    "list_semantic_feedback",
    "get_semantic_feedback",
    "record_semantic_feedback_resolution",
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
    "submit_modeling_batch",
    "get_modeling_batch",
    "list_session_modeling_batches",
    "list_ontology_modeling_batches",
    "get_modeling_context",
    "get_entity_statement_context",
    "get_ontology_read_model",
    "create_modeling_workflow_artifact",
    "get_modeling_workflow_artifact",
    "list_modeling_workflow_artifacts",
    "record_modeling_execution_event",
    "get_modeling_execution_event",
    "list_modeling_execution_events",
    "export_modeling_workflow_record",
    "repair_ontology_workspace",
    "get_ontology_workspace_context",
    "get_project_brief",
    "save_interview_answer",
    "update_project_brief",
    "list_competency_questions",
    "propose_competency_questions",
    "validate_competency_question",
    "semantic_sparql_query",
    "query_semantic_context",
    "discover_semantic_scopes",
    "submit_semantic_edit",
    "list_semantic_edit_audits",
    "get_semantic_governance_status",
    "get_semantic_read_model",
    "export_semantic_ontology",
    "inspect_semantic_projection_status",
    "start_semantic_projection_job",
    "preflight_semantic_migration",
    "create_semantic_migration_run",
    "run_next_semantic_migration_batch",
    "run_semantic_migration_parity_check",
    "cutover_semantic_migration_run",
    "rollback_semantic_migration_run",
    "compile_and_apply_canonical_command",
    "list_semantic_protection_sets",
    "create_semantic_protection_set",
    "update_semantic_protection_set",
    "delete_semantic_protection_set",
    "add_semantic_protection_set_members",
    "remove_semantic_protection_set_members",
}


# Tools that must never come back: legacy governance/publication/catalog/
# graph/documents/facts machinery is gone for good post-B2.
FORBIDDEN_TOOLS = {
    "check_semantic_staleness",
    "get_semantic_reasoning_run",
    "get_semantic_validation_run",
    "list_semantic_derived_pointers",
    "list_semantic_reasoning_runs",
    "list_semantic_validation_runs",
    "run_semantic_reasoning",
    "run_semantic_validation",

    "submit_semantic_rule_definition",
    "run_semantic_rule",
    "get_semantic_rule_definition",
    "get_ontology_lineage",
    "create_evidence_reference",
    "list_evidence_references",
    "get_evidence_reference",
    "associate_evidence_reference",
    "inspect_semantic_statement_provenance",
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


def test_submit_modeling_batch_schema_exposes_nested_modeling_items() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["submit_modeling_batch"].inputSchema or {}
    items = schema["properties"]["items"]
    item_ref = items["items"]["$ref"]
    assert item_ref.startswith("#/$defs/")
    item = schema["$defs"][item_ref.removeprefix("#/$defs/")]
    assert {"client_item_id", "command_kind", "payload"} <= set(item["required"])
    assert item["properties"]["payload"]["type"] == "object"
    assert set(item["properties"]) == {
        "client_item_id",
        "command_kind",
        "payload",
        "depends_on",
        "rationale",
        "competency_question_ids",
    }
    assert item["additionalProperties"] is False
    assert (
        item["properties"]["command_kind"]["enum"]
        == ModelingCommandHandlerRegistry(Settings()).command_kinds
    )
    guidance = item["properties"]["payload"]["description"]
    for required_phrase in (
        "create_class: name",
        "create_property: class_id, name, plus datatype or object_class_id",
        "create_relation_type: name, source_class_id, target_class_id",
        "create_entity: class_iri_or_legacy_id, label",
        "properties must be a JSON object mapping property IRI keys to values, and lists are invalid",
        "create_relation: source_entity_iri, relation_type_iri, target_entity_iri",
        "add_* aliases are forbidden",
    ):
        assert required_phrase in guidance


def test_get_semantic_read_model_accepts_optional_entity_iri() -> None:
    """R3.0-003: the MCP read-model tool exposes the detail-template
    entity_iri passthrough as an optional trailing parameter."""
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["get_semantic_read_model"].inputSchema or {}
    entity = schema["properties"]["entity_iri"]
    assert entity.get("default") is None
    assert {"type": "string"} in entity.get("anyOf", [])
    assert "entity_iri" not in schema.get("required", [])
    assert list(schema["properties"])[-1] == "entity_iri"


def test_mcp_ontology_read_model_forwards_r4010_exact_detail_name(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    """The MCP adapter must expose the same exact mapping detail models as REST."""
    from app.api.modeling_batches import READ_MODEL_NAMES

    mapping_models = {
        "table-mapping-list",
        "table-mapping-detail",
        "join-mapping-list",
        "join-mapping-detail",
        "enum-meaning-list",
        "enum-meaning-detail",
        "metric-list",
        "metric-detail",
    }
    assert mapping_models <= set(READ_MODEL_NAMES)

    in_memory_session.add_all(
        [
            ProjectModel(id="p-r4010", name="R4010", normalized_label="r4010"),
            OntologyModel(id="o-r4010", project_id="p-r4010", name="R4010 ontology"),
        ]
    )
    in_memory_session.commit()
    mcp_principal_factory(in_memory_session, project_id="p-r4010", scopes=["read"])
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, None))

    captured: dict[str, object] = {}

    def fake_read_model_adapter(**kwargs):
        captured.update(kwargs)
        return {
            "model_name": kwargs["model_name"],
            "items": [{"iri": kwargs["entity_iri"], "detail_fields": {"mapping_definition": {}}}],
            "warnings": [],
        }

    monkeypatch.setattr(
        "app.mcp.tools.modeling_batches.read_model_adapter", fake_read_model_adapter
    )
    tool = mcp._tool_manager.get_tool("get_ontology_read_model")  # noqa: SLF001
    assert tool is not None
    resource_iri = "https://r4010.test/metric/public-count"
    result = tool.fn(
        ontology_id="o-r4010",
        model_name="metric-detail",
        entity_iri=resource_iri,
    )

    assert result["ok"] is True, result
    assert captured["model_name"] == "metric-detail"
    assert captured["entity_iri"] == resource_iri


# --- get_entity_statement_context: optional version binds current -------------
#
# Read-only first pages bind the authoritative current workspace version when
# the caller omits it; an explicit version stays strictly drift-checked so the
# production delete-impact callers keep their exact snapshot binding.


class _StatementRows:
    """RdfStoreRepository stand-in serving canned statement bindings."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def query_read_model(self, **_kwargs):
        return SimpleNamespace(bindings=list(self.rows))


def _entity_statement_rows(
    entity_iri: str = "https://esc.test/entity/live-1",
) -> list[dict[str, object]]:
    return [
        {
            "subject": {"value": entity_iri, "type": "uri"},
            "predicate": {"value": "https://esc.test/p/label", "type": "uri"},
            "object": {"value": "Live one", "type": "literal"},
            "graph": {"value": "https://esc.test/g/asserted", "type": "uri"},
        },
        {
            "subject": {"value": entity_iri, "type": "uri"},
            "predicate": {"value": "https://esc.test/p/code", "type": "uri"},
            "object": {"value": "L1", "type": "literal"},
            "graph": {"value": "https://esc.test/g/asserted", "type": "uri"},
        },
        {
            "subject": {"value": "https://esc.test/entity/other", "type": "uri"},
            "predicate": {"value": "https://esc.test/p/linked", "type": "uri"},
            "object": {"value": entity_iri, "type": "uri"},
            "graph": {"value": "https://esc.test/g/asserted", "type": "uri"},
        },
    ]


def _entity_statement_tool(in_memory_session, mcp_principal_factory, monkeypatch):
    """Bind one ready workspace and a canned RDF store for statement reads."""
    from app.services.modeling_workspace import OntologyModelRevisionService
    from app.services.ontology_workspace import OntologyWorkspaceService

    in_memory_session.add_all(
        [
            ProjectModel(id="p-esc", name="ESC", normalized_label="esc"),
            OntologyModel(id="o-esc", project_id="p-esc", name="ESC ontology"),
        ]
    )
    in_memory_session.commit()
    OntologyWorkspaceService(in_memory_session, Settings()).ensure(
        in_memory_session.get(OntologyModel, "o-esc")
    )
    in_memory_session.commit()
    mcp_principal_factory(in_memory_session, project_id="p-esc", scopes=["read"])
    factory = sessionmaker(
        bind=in_memory_session.get_bind(), autoflush=False, autocommit=False
    )
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, None))
    store = _StatementRows(_entity_statement_rows())
    monkeypatch.setattr(
        "app.mcp.tools.modeling_batches.RdfStoreRepository", lambda _url: store
    )
    version = OntologyModelRevisionService(in_memory_session, Settings()).version_for(
        "o-esc"
    )
    tool = mcp._tool_manager.get_tool("get_entity_statement_context")  # noqa: SLF001
    assert tool is not None
    return tool.fn, version, store


def test_get_entity_statement_context_model_revision_is_optional() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["get_entity_statement_context"].inputSchema or {}
    assert set(schema.get("required", [])) == {"ontology_id", "entity_iri"}
    version = schema["properties"]["model_revision"]
    assert version.get("default") is None
    assert {"type": "integer"} in version.get("anyOf", [])


def test_entity_statement_context_omitted_version_binds_current(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    invoke, version, _store = _entity_statement_tool(
        in_memory_session, mcp_principal_factory, monkeypatch
    )
    result = invoke(ontology_id="o-esc", entity_iri="https://esc.test/entity/live-1")
    assert result["ok"] is True, result
    data = result["data"]
    assert data["model_revision"] == version
    assert data["complete"] is True
    assert len(data["statements"]) == 3


def test_entity_statement_context_explicit_version_stays_strict(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    invoke, version, _store = _entity_statement_tool(
        in_memory_session, mcp_principal_factory, monkeypatch
    )
    entity = "https://esc.test/entity/live-1"
    current = invoke(ontology_id="o-esc", entity_iri=entity, model_revision=version)
    assert current["ok"] is True, current
    stale = invoke(ontology_id="o-esc", entity_iri=entity, model_revision=version + 1)
    assert stale["ok"] is False
    assert "drifted" in stale["error"]


@pytest.mark.parametrize("invalid", ["legacy-hash", "0", True, -1])
def test_entity_statement_context_rejects_non_revision_bindings(
    invalid, in_memory_session, monkeypatch, mcp_principal_factory
):
    invoke, _version, _store = _entity_statement_tool(
        in_memory_session, mcp_principal_factory, monkeypatch
    )
    result = invoke(ontology_id="o-esc", entity_iri="https://esc.test/entity/live-1",
                    model_revision=invalid)
    assert result["ok"] is False
    assert "nonnegative integer" in result["error"]


def test_entity_statement_context_cursor_binds_version_entity_and_snapshot(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    invoke, version, store = _entity_statement_tool(
        in_memory_session, mcp_principal_factory, monkeypatch
    )
    entity = "https://esc.test/entity/live-1"
    first = invoke(ontology_id="o-esc", entity_iri=entity, page_size=2)
    assert first["ok"] is True, first
    assert first["data"]["complete"] is False
    cursor = first["data"]["next_cursor"]
    assert cursor
    # The bound version stays authoritative through pagination even when the
    # caller never restates it.
    second = invoke(ontology_id="o-esc", entity_iri=entity, page_size=2, cursor=cursor)
    assert second["ok"] is True, second
    assert second["data"]["complete"] is True
    assert len(second["data"]["statements"]) == 1
    assert second["data"]["model_revision"] == version
    # An explicit restatement must stay strict mid-pagination.
    stale = invoke(
        ontology_id="o-esc",
        entity_iri=entity,
        page_size=2,
        cursor=cursor,
        model_revision=version + 1,
    )
    assert stale["ok"] is False
    assert "drifted" in stale["error"]
    # The cursor never crosses to another entity.
    cross = invoke(
        ontology_id="o-esc",
        entity_iri="https://esc.test/entity/other",
        page_size=2,
        cursor=cursor,
    )
    assert cross["ok"] is False
    assert "drifted" in cross["error"]
    # A mutated snapshot invalidates the cursor through its digest binding.
    store.rows = _entity_statement_rows() + [
        {
            "subject": {"value": entity, "type": "uri"},
            "predicate": {"value": "https://esc.test/p/extra", "type": "uri"},
            "object": {"value": "late", "type": "literal"},
            "graph": {"value": "https://esc.test/g/asserted", "type": "uri"},
        }
    ]
    mutated = invoke(ontology_id="o-esc", entity_iri=entity, page_size=2, cursor=cursor)
    assert mutated["ok"] is False
    assert "drifted" in mutated["error"]
