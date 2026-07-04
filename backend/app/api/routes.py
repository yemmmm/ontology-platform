from fastapi import APIRouter, Depends
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver, get_rdf_store
from app.api.agent_test import router as agent_test_router
from app.api.catalog import router as catalog_router
from app.api.consistency import router as consistency_router
from app.api.documents import router as documents_router
from app.api.facts import router as facts_router
from app.api.graph import router as graph_router
from app.api.governance import router as governance_router
from app.api.import_export import router as import_export_router
from app.api.interview import router as interview_router
from app.api.metadata import router as metadata_router
from app.api.semantic import router as semantic_router
from app.repositories.rdf_store import RdfStoreRepository
from app.services.health import check_neo4j, check_oxigraph, check_postgres

router = APIRouter()
router.include_router(metadata_router)
router.include_router(catalog_router)
router.include_router(graph_router)
router.include_router(import_export_router)
router.include_router(agent_test_router)
router.include_router(consistency_router)
router.include_router(governance_router)
router.include_router(interview_router)
router.include_router(documents_router)
router.include_router(facts_router)
router.include_router(semantic_router)


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
