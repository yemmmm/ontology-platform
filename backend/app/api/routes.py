from fastapi import APIRouter, Depends
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver, get_rdf_store
from app.api.interview import router as interview_router
from app.api.ontologies import router as ontologies_router
from app.api.semantic import router as semantic_router
from app.api.agent_test import router as agent_test_router
from app.api.evidence import router as evidence_router
from app.repositories.rdf_store import RdfStoreRepository
from app.services.health import check_neo4j, check_oxigraph, check_postgres

router = APIRouter()
router.include_router(ontologies_router)
router.include_router(agent_test_router)
router.include_router(interview_router)
router.include_router(semantic_router)
router.include_router(evidence_router)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/postgres")
def postgres_health(session: Session = Depends(get_db_session)) -> dict[str, str]:
    return check_postgres(session)


@router.get("/health/neo4j")
def neo4j_health(driver: Driver = Depends(get_neo4j_driver)) -> dict[str, str]:
    return check_neo4j(driver)


@router.get("/health/dependencies")
def dependency_health(
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
) -> dict[str, dict[str, str]]:
    oxigraph_status: dict[str, str]
    try:
        oxigraph_status = check_oxigraph(rdf_store)
    except Exception as exc:
        oxigraph_status = {"status": "error", "detail": str(exc)}
    return {
        "postgres": check_postgres(session),
        "neo4j": check_neo4j(driver),
        "oxigraph": oxigraph_status,
    }
