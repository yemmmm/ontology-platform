from fastapi import APIRouter, Depends, status
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
from app.api.schemas import (
    OntologyVersionCreate,
    OntologyVersionRead,
    ProposalCreate,
    ProposalRead,
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


@router.post("/proposals/{proposal_id}/validate", response_model=ProposalRead)
def validate_proposal(proposal_id: str, session: Session = Depends(get_db_session)):
    service.validate_proposal(session, proposal_id)
    return service.proposal_detail(session, proposal_id)


@router.post("/proposals/{proposal_id}/review", response_model=ProposalRead)
def review_proposal(
    proposal_id: str,
    payload: ReviewDecisionCreate,
    session: Session = Depends(get_db_session),
):
    service.review_proposal(session, proposal_id, payload)
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
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.publish_version(session, driver, version_id)
