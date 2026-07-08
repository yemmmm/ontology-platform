from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreRepository
from app.repositories.postgres import create_session_factory
from app.services.embedding import EmbeddingClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_embedding_client(request: Request) -> EmbeddingClient:
    return request.app.state.embedding_client


def get_rdf_store(request: Request) -> RdfStoreRepository:
    return request.app.state.rdf_store


def build_session_factory(settings: Settings):
    return create_session_factory(settings)


def build_rdf_store(settings: Settings) -> RdfStoreRepository:
    return RdfStoreRepository(settings.oxigraph_url)
