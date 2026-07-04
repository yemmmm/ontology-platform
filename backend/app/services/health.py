from neo4j import Driver
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.neo4j import verify_neo4j
from app.repositories.rdf_store import RdfStoreRepository


def check_postgres(session: Session) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}


def check_neo4j(driver: Driver) -> dict[str, str]:
    verify_neo4j(driver)
    return {"status": "ok"}


def check_oxigraph(rdf_store: RdfStoreRepository) -> dict[str, str]:
    return rdf_store.health()
