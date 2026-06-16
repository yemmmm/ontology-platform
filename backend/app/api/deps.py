from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from neo4j import Driver
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.neo4j import create_neo4j_driver
from app.repositories.postgres import create_session_factory

admin_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_admin_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_bearer),
) -> None:
    settings: Settings = request.app.state.settings
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    if credentials.credentials != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token",
        )


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_neo4j_driver(request: Request) -> Driver:
    return request.app.state.neo4j_driver


def build_session_factory(settings: Settings):
    return create_session_factory(settings)


def build_neo4j_driver(settings: Settings) -> Driver:
    return create_neo4j_driver(settings)
