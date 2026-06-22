from fastapi import APIRouter, Depends, status
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_embedding_client, get_neo4j_driver
from app.api.schemas import OntologyExportRead, OntologyImportPayload
from app.services import import_export as service
from app.services.embedding import EmbeddingClient

router = APIRouter(tags=["import-export"])


@router.get("/ontologies/{ontology_id}/export", response_model=OntologyExportRead)
def export_ontology(
    ontology_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.export_ontology(session, driver, ontology_id)


@router.post(
    "/projects/{project_id}/ontologies/import",
    response_model=OntologyExportRead,
    status_code=status.HTTP_201_CREATED,
)
def import_ontology(
    project_id: str,
    payload: OntologyImportPayload,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    return service.import_ontology(session, driver, project_id, payload, embedding_client)
