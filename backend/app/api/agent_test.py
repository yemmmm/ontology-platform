from fastapi import APIRouter, Depends
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db_session,
    get_embedding_client,
    get_neo4j_driver,
    get_rdf_store,
    get_settings,
)
from app.api.schemas import AgentTestRequest, AgentTestResponse
from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreRepository
from app.services import agent_test as service
from app.services.embedding import EmbeddingClient
from app.services.semantic_read_model import SemanticReadModelService
from app.services.semantic_read_scope import SemanticReadScopeResolver

router = APIRouter(tags=["agent-test"])


def _read_model_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticReadModelService:
    """Construct the Stage 4 read-model service used by agent-test.

    Mirrors the construction in ``app/api/semantic.py`` so the agent-test
    endpoint sees the same composer registry as the read-model route."""
    return SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=SemanticReadScopeResolver(session),
        session=session,
    )


@router.post("/agent-test/run", response_model=AgentTestResponse)
def run_agent_test(
    payload: AgentTestRequest,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    settings: Settings = Depends(get_settings),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
):
    read_model_service = _read_model_service(session, rdf_store, settings)
    return service.run_agent_test(
        session=session,
        driver=driver,
        settings=settings,
        payload=payload,
        embedding_client=embedding_client,
        read_model_service=read_model_service,
    )
