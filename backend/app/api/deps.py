from collections.abc import Generator

from fastapi import Request
from neo4j import Driver
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.neo4j import create_neo4j_driver
from app.repositories.postgres import create_session_factory
from app.services.embedding import EmbeddingClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_neo4j_driver(request: Request) -> Driver:
    return request.app.state.neo4j_driver


def get_embedding_client(request: Request) -> EmbeddingClient:
    return request.app.state.embedding_client


def build_session_factory(settings: Settings):
    return create_session_factory(settings)


def build_neo4j_driver(settings: Settings) -> Driver:
    return create_neo4j_driver(settings)
