from fastapi import HTTPException, status
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings


class Base(DeclarativeBase):
    pass


def create_session_factory(settings: Settings) -> sessionmaker:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def assert_version_mutable(session: Session, version_id: str):
    """Repository boundary guard used by every version-scoped write path."""
    from app.repositories.models import OntologyVersionModel, VersionStatus

    version = session.get(OntologyVersionModel, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ontology version not found")
    if version.status != VersionStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published or deprecated ontology versions are immutable",
        )
    return version


@event.listens_for(Session, "before_flush")
def protect_published_versions(session: Session, _flush_context, _instances) -> None:
    """Last-line invariant: ORM callers cannot bypass service-layer immutability checks."""
    from app.repositories.models import (
        ClassModel,
        ConstraintModel,
        OntologyModel,
        OntologyVersionModel,
        PropertyDefModel,
        RelationTypeModel,
        VersionStatus,
    )

    for version in set(session.dirty) | set(session.deleted):
        if not isinstance(version, OntologyVersionModel):
            continue
        history = inspect(version).attrs.status.history
        publishing_now = (
            version.status == VersionStatus.PUBLISHED.value
            and VersionStatus.DRAFT.value in history.deleted
        )
        if version.status != VersionStatus.DRAFT.value and not publishing_now:
            raise HTTPException(status_code=409, detail="Published ontology versions are immutable")

    ontology_ids: set[str] = set()
    for value in set(session.new) | set(session.dirty) | set(session.deleted):
        if isinstance(value, (ClassModel, ConstraintModel, RelationTypeModel)):
            ontology_ids.add(value.ontology_id)
        elif isinstance(value, PropertyDefModel):
            class_ = value.class_ or session.get(ClassModel, value.class_id)
            if class_ is not None:
                ontology_ids.add(class_.ontology_id)
    for ontology_id in ontology_ids:
        ontology = session.get(OntologyModel, ontology_id)
        if ontology is not None and ontology.current_version_id:
            assert_version_mutable(session, ontology.current_version_id)
