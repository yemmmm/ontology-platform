import json
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from neo4j import Driver
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.repositories.neo4j import create_neo4j_driver, ensure_graph_constraints
from app.repositories.postgres import create_session_factory
from app.services import graph as graph_service
from app.services import governance as governance_service
from app.services import documents as document_service
from app.api.schemas import (
    CompetencyQuestionCreate,
    CompetencyQuestionRead,
    InterviewAnswerCreate,
    InterviewAnswerRead,
    ProjectBriefUpdate,
    ProposalCreate,
)
from app.services.embedding import EmbeddingClient
from app.services import interview as interview_service

mcp = FastMCP("ontology-platform")

_settings: Settings | None = None
_session_factory: sessionmaker | None = None
_driver: Driver | None = None
_embedding_client: EmbeddingClient | None = None

T = TypeVar("T")


def _jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def _resources() -> tuple[sessionmaker, Driver, EmbeddingClient]:
    global _settings, _session_factory, _driver, _embedding_client
    if _settings is None:
        _settings = Settings()
    if _session_factory is None:
        _session_factory = create_session_factory(_settings)
    if _driver is None:
        _driver = create_neo4j_driver(_settings)
        ensure_graph_constraints(_driver, _settings.embedding_dimensions)
    if _embedding_client is None:
        _embedding_client = EmbeddingClient(_settings)
    return _session_factory, _driver, _embedding_client


def _run_tool(fn: Callable[[Session, Driver, EmbeddingClient], T]) -> dict[str, Any]:
    session_factory, driver, embedding_client = _resources()
    try:
        with session_factory() as session:
            return {"ok": True, "data": _jsonable(fn(session, driver, embedding_client))}
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {"ok": False, "error": detail, "status_code": exc.status_code}
    except Exception as exc:  # MCP tools should return structured failures.
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def search_entities(
    query: str,
    ontology_id: str | None = None,
    class_id: str | None = None,
    limit: int = 10,
    mode: str = "hybrid",
) -> dict[str, Any]:
    """Recall graph entities globally with optional ontology and class filters."""
    return _run_tool(
        lambda session, driver, embedding_client: graph_service.search_all_entities(
            session,
            driver,
            query,
            class_id,
            ontology_id,
            limit,
            mode,
            embedding_client,
        ),
    )


@mcp.tool()
def get_entity(
    ontology_id: str,
    entity_id: str,
    include_relations: bool = True,
    relation_limit: int = 50,
) -> dict[str, Any]:
    """Fetch one entity and, optionally, its incoming/outgoing relations."""
    return _run_tool(
        lambda session, driver, _embedding_client: graph_service.get_entity_with_relations(
            session,
            driver,
            ontology_id,
            entity_id,
            include_relations,
            relation_limit,
        ),
    )


@mcp.tool()
def find_related_entities(
    ontology_id: str,
    entity_id: str,
    depth: int = 1,
    direction: str = "both",
    relation_type_ids: list[str] | None = None,
    target_class_ids: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find graph neighbors for an entity with semantic filters."""
    return _run_tool(
        lambda session, driver, _embedding_client: graph_service.find_related_entities(
            session,
            driver,
            ontology_id,
            entity_id,
            depth,
            direction,
            relation_type_ids,
            target_class_ids,
            limit,
        ),
    )


@mcp.tool()
def validate_entity(
    ontology_id: str,
    class_id: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Validate entity properties against effective ontology class schema."""
    return _run_tool(
        lambda session, _driver, _embedding_client: graph_service.validate_entity_payload(
            session,
            ontology_id,
            class_id,
            properties,
        ),
    )


@mcp.tool()
def explain_entity(
    ontology_id: str,
    entity_id: str,
    depth: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Return one entity with schema, relation context, and a short explanation."""
    return _run_tool(
        lambda session, driver, _embedding_client: graph_service.explain_entity(
            session,
            driver,
            ontology_id,
            entity_id,
            depth,
            limit,
        ),
    )


@mcp.tool()
def submit_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """Submit an idempotent, version-scoped governance proposal; never writes formal data."""
    return _run_tool(
        lambda session, _driver, _embedding_client: governance_service.proposal_detail(
            session,
            governance_service.create_proposal(session, ProposalCreate.model_validate(proposal)).id,
        )
    )


@mcp.tool()
def propose_schema_changes(proposal: dict[str, Any]) -> dict[str, Any]:
    """Submit a governed Schema candidate batch; never writes formal Schema directly."""
    return _propose_knowledge(proposal, "schema_change")


@mcp.tool()
def validate_proposal(proposal_id: str) -> dict[str, Any]:
    """Run deterministic validation for a proposed batch."""
    return _run_tool(
        lambda session, driver, _embedding_client: governance_service.proposal_detail(
            session, governance_service.validate_proposal(session, proposal_id, driver).id
        )
    )


@mcp.tool()
def validate_draft(version_id: str) -> dict[str, Any]:
    """Validate every editable proposal for a draft and return deterministic results."""

    def validate(session: Session, driver: Driver, _embedding_client: EmbeddingClient) -> Any:
        proposals = governance_service.list_version_proposals(session, version_id)
        results = []
        for proposal in proposals:
            if proposal.status == "proposed":
                governance_service.validate_proposal(session, proposal.id, driver)
            detail = governance_service.proposal_detail(session, proposal.id)
            results.append(
                {
                    "proposal_id": proposal.id,
                    "proposal_type": proposal.proposal_type,
                    "status": detail["status"],
                    "validation_result": detail["validation_result"],
                }
            )
        return {"version_id": version_id, "proposals": results}

    return _run_tool(validate)


@mcp.tool()
def get_proposal_status(proposal_id: str) -> dict[str, Any]:
    """Read the complete proposal audit trail and evidence chain."""
    return _run_tool(
        lambda session, _driver, _embedding_client: governance_service.proposal_detail(
            session, proposal_id
        )
    )


@mcp.tool()
def list_review_items(ontology_id: str) -> dict[str, Any]:
    """List review batches with counts and exact workbench deep links."""
    return _run_tool(
        lambda session, _driver, _embedding_client: governance_service.list_review_batches(
            session, ontology_id
        )
    )


@mcp.tool()
def get_review_batch(review_batch_id: str) -> dict[str, Any]:
    """Read one stable review batch, its status, counts, and workbench deep link."""
    return _run_tool(
        lambda session, _driver, _embedding_client: governance_service.get_review_batch(
            session, review_batch_id
        )
    )


@mcp.tool()
def get_review_workspace_link(review_batch_id: str) -> dict[str, Any]:
    """Return the exact platform workbench link for a review batch."""

    def link(session: Session, _driver: Driver, _embedding_client: EmbeddingClient) -> Any:
        batch = governance_service.get_review_batch(session, review_batch_id)
        return {"review_batch_id": review_batch_id, "deep_link": batch["deep_link"]}

    return _run_tool(link)


@mcp.tool()
def get_build_context(project_id: str) -> dict[str, Any]:
    """Read durable project, interview, ontology, and question workflow state."""
    return _run_tool(
        lambda session, _driver, _embedding_client: interview_service.get_build_context(
            session, project_id
        )
    )


@mcp.tool()
def get_project_brief(project_id: str) -> dict[str, Any]:
    """Read Project Brief completeness and up to three high-value clarification items."""
    return _run_tool(
        lambda session, _driver, _embedding_client: interview_service.get_project_brief(
            session, project_id
        )
    )


@mcp.tool()
def save_interview_answer(
    project_id: str,
    answer: str,
    source_type: str = "conversation",
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Save a user answer so Project Brief fields and questions can cite it."""
    return _run_tool(
        lambda session, _driver, _embedding_client: InterviewAnswerRead.model_validate(
            interview_service.create_answer(
                session,
                project_id,
                InterviewAnswerCreate(answer=answer, source_type=source_type, actor_id=actor_id),
            )
        ).model_dump()
    )


@mcp.tool()
def update_project_brief(project_id: str, update: dict[str, Any]) -> dict[str, Any]:
    """Update and confirm interview fields with saved-answer source links."""
    return _run_tool(
        lambda session, _driver, _embedding_client: interview_service.update_project_brief(
            session, project_id, ProjectBriefUpdate.model_validate(update)
        )
    )


@mcp.tool()
def list_competency_questions(
    project_id: str, include_inactive: bool = False
) -> dict[str, Any]:
    """List ordered competency questions and their validation states."""
    return _run_tool(
        lambda session, _driver, _embedding_client: [
            CompetencyQuestionRead.model_validate(item).model_dump()
            for item in interview_service.list_questions(session, project_id, include_inactive)
        ]
    )


@mcp.tool()
def propose_competency_questions(
    project_id: str, questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create ordered draft competency questions; this does not approve them."""
    return _run_tool(
        lambda session, _driver, _embedding_client: [
            CompetencyQuestionRead.model_validate(
                interview_service.create_question(
                    session, project_id, CompetencyQuestionCreate.model_validate(question)
                )
            ).model_dump()
            for question in questions
        ]
    )


@mcp.tool()
def list_source_documents(project_id: str) -> dict[str, Any]:
    """List uploaded sources and their deterministic parsing status."""
    return _run_tool(
        lambda session, _driver, _embedding_client: document_service.list_documents(
            session, project_id
        )
    )


@mcp.tool()
def get_source_document_status(document_id: str) -> dict[str, Any]:
    """Read parsing status, content identity, and chunk count for one source."""
    return _run_tool(
        lambda session, _driver, _embedding_client: document_service.get_document(
            session, document_id
        )
    )


def _propose_knowledge(proposal: dict[str, Any], expected_type: str) -> dict[str, Any]:
    def create(session: Session, _driver: Driver, _embedding_client: EmbeddingClient) -> Any:
        payload = ProposalCreate.model_validate({**proposal, "proposal_type": expected_type})
        created = governance_service.create_proposal(session, payload)
        return governance_service.proposal_detail(session, created.id)

    return _run_tool(create)


@mcp.tool()
def propose_entities(proposal: dict[str, Any]) -> dict[str, Any]:
    """Submit evidence-bound entity candidates; never merges or writes graph data directly."""
    return _propose_knowledge(proposal, "entity")


@mcp.tool()
def propose_relations(proposal: dict[str, Any]) -> dict[str, Any]:
    """Submit evidence-bound relation candidates against an existing RelationType."""
    return _propose_knowledge(proposal, "relation")


@mcp.tool()
def propose_entity_merges(proposal: dict[str, Any]) -> dict[str, Any]:
    """Submit possible duplicate entities for explicit human review; does not merge them."""
    return _propose_knowledge(proposal, "merge")


@mcp.tool()
def validate_competency_question(question_id: str) -> dict[str, Any]:
    """Run the bound query definition and record pass/fail result."""
    return _run_tool(
        lambda session, driver, _embedding_client: interview_service.run_question_validation(
            session, driver, question_id
        )
    )


@mcp.tool()
def generate_fact_claims(version_id: str) -> dict[str, Any]:
    """Deterministically regenerate structured Fact Claims from the draft graph."""
    from app.services import facts as facts_service

    return _run_tool(
        lambda session, driver, _embedding_client: [
            {
                "id": c.id,
                "claim_key": c.claim_key,
                "layer": c.layer,
                "claim_type": c.claim_type,
                "subject": c.subject,
                "predicate": c.predicate,
                "value": c.value,
                "graph_path": c.graph_path,
                "evidence_ids": c.evidence_ids,
                "generation_reason": c.generation_reason,
                "confidence": c.confidence,
                "audit_status": c.audit_status,
                "stale": c.stale,
                "stale_reason": c.stale_reason,
            }
            for c in facts_service.generate_fact_claims(session, driver, version_id)
        ]
    )


@mcp.tool()
def list_fact_claims(
    version_id: str, layer: str | None = None, claim_type: str | None = None
) -> dict[str, Any]:
    """List structured Fact Claims stratified by audit layer."""
    from app.services import facts as facts_service

    return _run_tool(
        lambda session, _driver, _embedding_client: [
            {
                "id": c.id,
                "layer": c.layer,
                "claim_type": c.claim_type,
                "subject": c.subject,
                "predicate": c.predicate,
                "value": c.value,
                "audit_status": c.audit_status,
                "stale": c.stale,
                "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
            }
            for c in facts_service.list_fact_claims(session, version_id, layer, claim_type)
        ]
    )


@mcp.tool()
def sample_fact_claims(
    version_id: str, config: dict[str, int] | None = None
) -> dict[str, Any]:
    """Return a stratified fact sample for human audit."""
    from app.services import facts as facts_service

    return _run_tool(
        lambda session, _driver, _embedding_client: [
            {
                "id": c.id,
                "layer": c.layer,
                "claim_type": c.claim_type,
                "subject": c.subject,
                "predicate": c.predicate,
                "value": c.value,
                "audit_status": c.audit_status,
                "stale": c.stale,
            }
            for c in facts_service.sample_fact_claims(session, version_id, config)
        ]
    )


@mcp.tool()
def get_publication_readiness(version_id: str) -> dict[str, Any]:
    """Evaluate structured publication gates and return blocking items."""
    from app.services import publication as publication_service

    return _run_tool(
        lambda session, driver, _embedding_client: publication_service.evaluate_readiness(
            session, driver, version_id
        )
    )


if __name__ == "__main__":
    mcp.run()
