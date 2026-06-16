from fastapi import FastAPI

from app.api.deps import build_neo4j_driver, build_session_factory
from app.api.routes import router
from app.core.config import Settings
from app.repositories.neo4j import ensure_graph_constraints


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="Ontology Platform API", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = build_session_factory(settings)
    app.state.neo4j_driver = build_neo4j_driver(settings)
    app.include_router(router, prefix="/api")

    @app.on_event("startup")
    def initialize_graph() -> None:
        ensure_graph_constraints(app.state.neo4j_driver)

    @app.on_event("shutdown")
    def close_resources() -> None:
        app.state.neo4j_driver.close()

    return app


app = create_app()
