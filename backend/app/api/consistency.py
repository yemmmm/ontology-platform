from fastapi import APIRouter, Depends
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
from app.services import consistency as service

router = APIRouter(tags=["consistency"])


@router.get("/ontologies/{ontology_id}/graph-consistency")
def audit_graph_consistency(
    ontology_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.audit_ontology_graph(session, driver, ontology_id)


@router.post("/ontologies/{ontology_id}/graph-consistency/repair")
def repair_graph_consistency(
    ontology_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.repair_ontology_graph(session, driver, ontology_id)
