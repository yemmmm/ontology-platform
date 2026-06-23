from fastapi import APIRouter, Depends
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
from app.api.schemas import (
    FactClaimRead,
    FactClaimReviewCreate,
    FactClaimSampleCreate,
)
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
