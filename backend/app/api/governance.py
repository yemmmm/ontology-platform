from fastapi import APIRouter, Depends, status
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
from app.api.schemas import (
    ConflictResolutionCreate,
    KnowledgeConflictRead,
    OntologyVersionCreate,
    OntologyVersionRead,
    ProposalCreate,
    ProposalBatchReview,
    ProposalItemReview,
    ProposalRead,
    PublicationConfirm,
    PublicationReadinessRead,
    ReviewBatchRead,
    ReviewDecisionCreate,
    VersionDiffRead,
)
from app.services import governance as service

router = APIRouter(tags=["governance"])


@router.post(
    "/ontologies/{ontology_id}/versions",
    response_model=OntologyVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    ontology_id: str,
    payload: OntologyVersionCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_draft_version(session, ontology_id, payload.parent_version_id)


@router.get("/ontologies/{ontology_id}/versions", response_model=list[OntologyVersionRead])
def list_versions(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.list_versions(session, ontology_id)


@router.get("/versions/{from_id}/diff/{to_id}", response_model=VersionDiffRead)
def version_diff(
    from_id: str,
    to_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.version_diff(session, driver, from_id, to_id)


@router.post("/proposals", response_model=ProposalRead, status_code=status.HTTP_201_CREATED)
def create_proposal(payload: ProposalCreate, session: Session = Depends(get_db_session)):
    proposal = service.create_proposal(session, payload)
    return service.proposal_detail(session, proposal.id)


@router.get("/proposals/{proposal_id}", response_model=ProposalRead)
def get_proposal(proposal_id: str, session: Session = Depends(get_db_session)):
    return service.proposal_detail(session, proposal_id)


@router.get("/ontologies/{ontology_id}/proposals", response_model=list[ProposalRead])
def list_proposals(
    ontology_id: str,
    proposal_type: str | None = None,
    session: Session = Depends(get_db_session),
):
    return service.list_proposals(session, ontology_id, proposal_type)


@router.get("/ontologies/{ontology_id}/review-batches", response_model=list[ReviewBatchRead])
def list_review_batches(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.list_review_batches(session, ontology_id)


@router.get("/review-batches/{review_batch_id}", response_model=ReviewBatchRead)
def get_review_batch(review_batch_id: str, session: Session = Depends(get_db_session)):
    return service.get_review_batch(session, review_batch_id)


@router.post("/proposals/{proposal_id}/validate", response_model=ProposalRead)
def validate_proposal(
    proposal_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    service.validate_proposal(session, proposal_id, driver)
    return service.proposal_detail(session, proposal_id)


@router.post("/proposals/{proposal_id}/review", response_model=ProposalRead)
def review_proposal(
    proposal_id: str,
    payload: ReviewDecisionCreate,
    session: Session = Depends(get_db_session),
):
    service.review_proposal(session, proposal_id, payload)
    return service.proposal_detail(session, proposal_id)


@router.post("/proposals/{proposal_id}/items/{item_key}/review", response_model=ProposalRead)
def review_proposal_item(
    proposal_id: str,
    item_key: str,
    payload: ProposalItemReview,
    session: Session = Depends(get_db_session),
):
    service.review_proposal_item(session, proposal_id, item_key, payload)
    return service.proposal_detail(session, proposal_id)


@router.post("/proposals/{proposal_id}/items/review", response_model=ProposalRead)
def batch_review_proposal_items(
    proposal_id: str,
    payload: ProposalBatchReview,
    session: Session = Depends(get_db_session),
):
    service.batch_review_proposal_items(session, proposal_id, payload)
    return service.proposal_detail(session, proposal_id)


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalRead)
def apply_proposal(
    proposal_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    service.apply_proposal(session, driver, proposal_id)
    return service.proposal_detail(session, proposal_id)


@router.post("/versions/{version_id}/publish", response_model=OntologyVersionRead)
def publish_version(
    version_id: str,
    payload: PublicationConfirm,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.publish_version(session, driver, version_id, confirm=payload.confirm)


@router.get(
    "/versions/{version_id}/publication-readiness",
    response_model=PublicationReadinessRead,
)
def publication_readiness(
    version_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.get_publication_readiness(session, driver, version_id)


@router.get("/ontologies/{ontology_id}/knowledge-conflicts", response_model=list[KnowledgeConflictRead])
def list_knowledge_conflicts(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.list_conflicts(session, ontology_id)


@router.post("/knowledge-conflicts/{conflict_id}/resolve", response_model=KnowledgeConflictRead)
def resolve_knowledge_conflict(
    conflict_id: str,
    payload: ConflictResolutionCreate,
    session: Session = Depends(get_db_session),
):
    return service.resolve_conflict(
        session, conflict_id, payload.action, payload.value, payload.reviewer_id
    )
