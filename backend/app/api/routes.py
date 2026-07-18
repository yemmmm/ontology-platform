from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store
from app.api.auth import router as auth_router
from app.security.http import authorize_api_request
from app.api.interview import router as interview_router
from app.api.build_sessions import router as build_sessions_router
from app.api.ontologies import router as ontologies_router
from app.api.semantic import router as semantic_router
from app.api.agent_test import router as agent_test_router
from app.api.evidence import router as evidence_router
from app.api.evidence_references import router as evidence_references_router
from app.api.fact_evidence import router as fact_evidence_router
from app.api.mcp_catalog import router as mcp_catalog_router
from app.api.modeling_batches import router as modeling_batches_router
from app.api.modeling_workflow import router as modeling_workflow_router
from app.repositories.rdf_store import RdfStoreRepository
from app.services.health import check_oxigraph, check_postgres

router = APIRouter(dependencies=[Depends(authorize_api_request)])
router.include_router(auth_router)
router.include_router(ontologies_router)
router.include_router(agent_test_router)
router.include_router(interview_router)
router.include_router(build_sessions_router)
router.include_router(modeling_batches_router)
router.include_router(modeling_workflow_router)
router.include_router(semantic_router)
router.include_router(evidence_router)
router.include_router(evidence_references_router)
router.include_router(fact_evidence_router)
router.include_router(mcp_catalog_router)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/postgres")
def postgres_health(session: Session = Depends(get_db_session)) -> dict[str, str]:
    return check_postgres(session)


@router.get("/health/dependencies")
def dependency_health(
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
) -> dict[str, dict[str, str]]:
    oxigraph_status: dict[str, str]
    try:
        oxigraph_status = check_oxigraph(rdf_store)
    except Exception as exc:
        oxigraph_status = {"status": "error", "detail": str(exc)}
    return {
        "postgres": check_postgres(session),
        "oxigraph": oxigraph_status,
    }
