from fastapi import APIRouter, Depends, Response, status
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
from app.api.schemas import (
    ConflictResolutionCreate,
    KnowledgeConflictRead,
    OntologyVersionCreate,
    OntologyVersionRead,
    ProposalCreate,
    ProposalRead,
    PublicationConfirm,
    PublicationReadinessRead,
    VersionMutabilityUpdate,
    VersionDiffRead,
)
from app.services import governance as service
from app.services import publication as publication_service

router = APIRouter(tags=["governance"])

_LEGACY_SUNSET = "Sat, 1 Nov 2026 00:00:00 GMT"


def _mark_deprecated(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _LEGACY_SUNSET


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
def list_versions(
    ontology_id: str,
    session: Session = Depends(get_db_session),
    response: Response = None,
):
    if response is not None:
        _mark_deprecated(response)
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
def create_proposal(
    payload: ProposalCreate,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    proposal = service.create_proposal(session, payload, driver)
    return service.proposal_detail(session, proposal.id)


@router.get("/proposals/{proposal_id}", response_model=ProposalRead)
def get_proposal(proposal_id: str, session: Session = Depends(get_db_session)):
    return service.proposal_detail(session, proposal_id)


@router.get("/ontologies/{ontology_id}/proposals", response_model=list[ProposalRead])
def list_proposals(
    ontology_id: str,
    proposal_type: str | None = None,
    session: Session = Depends(get_db_session),
    response: Response = None,
):
    if response is not None:
        _mark_deprecated(response)
    return service.list_proposals(session, ontology_id, proposal_type)


@router.post("/proposals/{proposal_id}/validate", response_model=ProposalRead)
def validate_proposal(
    proposal_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    service.validate_proposal(session, proposal_id, driver)
    return service.proposal_detail(session, proposal_id)


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalRead)
def apply_proposal(
    proposal_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    service.apply_proposal(session, driver, proposal_id)
    return service.proposal_detail(session, proposal_id)


@router.patch("/versions/{version_id}/mutability", response_model=OntologyVersionRead)
def set_version_mutability(
    version_id: str,
    payload: VersionMutabilityUpdate,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.set_version_mutability(session, driver, version_id, payload.mutable)


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
    return publication_service.evaluate_readiness(session, driver, version_id)


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
