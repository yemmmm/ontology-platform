from fastapi import APIRouter, Depends
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
from app.api.agent_test import router as agent_test_router
from app.api.graph import router as graph_router
from app.api.import_export import router as import_export_router
from app.api.metadata import router as metadata_router
from app.services.health import check_neo4j, check_postgres

router = APIRouter()
router.include_router(metadata_router)
router.include_router(graph_router)
router.include_router(import_export_router)
router.include_router(agent_test_router)


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
) -> dict[str, dict[str, str]]:
    return {
        "postgres": check_postgres(session),
        "neo4j": check_neo4j(driver),
    }
