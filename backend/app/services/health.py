from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.rdf_store import RdfStoreRepository


def check_postgres(session: Session) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}


def check_oxigraph(rdf_store: RdfStoreRepository) -> dict[str, str]:
    return rdf_store.health()
