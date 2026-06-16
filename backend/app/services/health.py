from neo4j import Driver
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.neo4j import verify_neo4j


def check_postgres(session: Session) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}


def check_neo4j(driver: Driver) -> dict[str, str]:
    verify_neo4j(driver)
    return {"status": "ok"}
