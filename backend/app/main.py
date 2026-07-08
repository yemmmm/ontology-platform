from fastapi import FastAPI

from app.api.deps import build_rdf_store, build_session_factory
from app.api.routes import router
from app.core.config import Settings
from app.services.embedding import EmbeddingClient


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="Ontology Platform API", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = build_session_factory(settings)
    app.state.rdf_store = build_rdf_store(settings)
    app.state.embedding_client = EmbeddingClient(settings)
    app.include_router(router, prefix="/api")
    return app


app = create_app()
