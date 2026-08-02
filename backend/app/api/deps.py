from collections.abc import Generator
import threading

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreRepository
from app.repositories.postgres import create_session_factory
from app.services.embedding import EmbeddingClient
from app.services.semantic_context_cursor import ContextCursorCodec


_context_cursor_codec_lock = threading.Lock()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_context_cursor_codec(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ContextCursorCodec:
    """Return the cursor signer owned by this FastAPI application.

    An empty signing secret intentionally uses a process-local ephemeral token.
    Keeping that codec on the application lets a REST cursor survive the
    individual request/service lifetime while still isolating independent app
    instances.  ``settings`` is injected rather than read from ``app.state``
    so test and embedding applications can override the settings dependency.
    """
    codec = getattr(request.app.state, "context_cursor_codec", None)
    if codec is not None:
        return codec

    with _context_cursor_codec_lock:
        codec = getattr(request.app.state, "context_cursor_codec", None)
        if codec is None:
            codec = ContextCursorCodec.from_settings(settings)
            request.app.state.context_cursor_codec = codec
    return codec


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
