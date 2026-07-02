from fastapi import APIRouter, Depends, HTTPException
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
from app.api.schemas import (
    AssertionCreate,
    BackgroundKnowledgePromotionCreate,
    BackgroundKnowledgePromotionRead,
    BackgroundRecallCreate,
    EntityKnowledgeRecallCreate,
    FactClaimRead,
    FactClaimReviewCreate,
    FactClaimSampleCreate,
    RuleDefinitionCreate,
    RuleDefinitionRead,
    UnanchoredKnowledgeCreate,
    UnanchoredKnowledgeRead,
)
from app.services import governance as governance_service
from app.services import facts as service

router = APIRouter(tags=["fact audit"])


@router.post(
    "/versions/{version_id}/fact-claims:generate",
    response_model=list[FactClaimRead],
)
def generate_fact_claims(
    version_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.generate_fact_claims(session, driver, version_id)


@router.post("/versions/{version_id}/assertions", response_model=FactClaimRead)
def create_assertion(
    version_id: str,
    payload: AssertionCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_assertion(
        session,
        version_id,
        anchor=payload.anchor,
        subject=payload.subject,
        predicate=payload.predicate,
        value=payload.value,
        evidence_ids=payload.evidence_ids,
        generation_reason=payload.generation_reason,
        claim_type=payload.claim_type,
        layer=payload.layer,
        graph_path=payload.graph_path,
        confidence=payload.confidence,
        sensitivity=payload.sensitivity,
        access_policy=payload.access_policy,
        override_of_claim_id=payload.override_of_claim_id,
    )


@router.post(
    "/versions/{version_id}/background-knowledge",
    response_model=UnanchoredKnowledgeRead,
)
def save_background_knowledge(
    version_id: str,
    payload: UnanchoredKnowledgeCreate,
    session: Session = Depends(get_db_session),
):
    return service.save_unanchored_knowledge(
        session,
        version_id,
        text=payload.text,
        source=payload.source,
        summary=payload.summary,
        embedding=payload.embedding,
        tags=payload.tags,
        confidence=payload.confidence,
        applicability=payload.applicability,
    )


@router.post("/versions/{version_id}/background-knowledge:recall")
def recall_background_knowledge(
    version_id: str,
    payload: BackgroundRecallCreate,
    session: Session = Depends(get_db_session),
):
    return service.recall_background_knowledge(
        session,
        version_id,
        query=payload.query,
        query_embedding=payload.query_embedding,
        limit=payload.limit,
    )


@router.post(
    "/versions/{version_id}/background-knowledge/{knowledge_id}:promote",
    response_model=BackgroundKnowledgePromotionRead,
)
def promote_background_knowledge(
    version_id: str,
    knowledge_id: str,
    payload: BackgroundKnowledgePromotionCreate,
    session: Session = Depends(get_db_session),
):
    if payload.proposal.target_version_id != version_id:
        raise HTTPException(status_code=400, detail="Proposal target version must match URL version")
    service.get_background_knowledge(session, version_id, knowledge_id)
    proposal = governance_service.create_proposal(session, payload.proposal)
    knowledge = service.mark_background_knowledge_promoted(
        session,
        version_id,
        knowledge_id,
        proposal.id,
    )
    return {"knowledge": knowledge, "proposal": proposal}


@router.post("/versions/{version_id}/rule-definitions", response_model=RuleDefinitionRead)
def create_rule_definition(
    version_id: str,
    payload: RuleDefinitionCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_rule_definition(
        session,
        version_id,
        payload.model_dump(),
        status=payload.status,
    )


@router.post("/versions/{version_id}/rule-definitions:execute", response_model=list[FactClaimRead])
def execute_rule_definitions(
    version_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.execute_rule_definitions(session, driver, version_id)


@router.post("/versions/{version_id}/knowledge:recall")
def recall_entity_knowledge(
    version_id: str,
    payload: EntityKnowledgeRecallCreate,
    session: Session = Depends(get_db_session),
):
    return service.recall_entity_knowledge(
        session,
        version_id,
        payload.entity,
        background_query=payload.background_query,
        authorized=payload.authorized,
    )


@router.get("/versions/{version_id}/fact-claims", response_model=list[FactClaimRead])
def list_fact_claims(
    version_id: str,
    layer: str | None = None,
    claim_type: str | None = None,
    session: Session = Depends(get_db_session),
):
    return service.list_fact_claims(session, version_id, layer, claim_type)


@router.post("/versions/{version_id}/fact-claims:sample", response_model=list[FactClaimRead])
def sample_fact_claims(
    version_id: str,
    payload: FactClaimSampleCreate,
    session: Session = Depends(get_db_session),
):
    return service.sample_fact_claims(session, version_id, payload.config or None)


@router.post("/fact-claims/{claim_id}/review", response_model=FactClaimRead)
def review_fact_claim(
    claim_id: str,
    payload: FactClaimReviewCreate,
    session: Session = Depends(get_db_session),
):
    return service.review_fact_claim(
        session,
        claim_id,
        payload.decision,
        reviewer_id=payload.reviewer_id,
        reason=payload.reason,
        linked_fix_proposal_id=payload.linked_fix_proposal_id,
    )
