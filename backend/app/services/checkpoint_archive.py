"""The source Project of a checkpoint fork remains readable evidence."""

from sqlalchemy import select

from app.repositories.models import OntologyModel, ProjectModel, SemanticGraphRegistryModel

ARCHIVE_KEY = "checkpoint_fork_archive"


def project_is_checkpoint_archived(session, project_id: str) -> bool:
    return any(
        (ontology.external_mappings or {}).get(ARCHIVE_KEY)
        for ontology in session.scalars(
            select(OntologyModel).where(OntologyModel.project_id == project_id)
        )
    )


def lock_graph_owners(session, graph_iris: list[str]):
    """Match checkpoint capture's lock order before mutating an owned graph."""
    owners = select(SemanticGraphRegistryModel.semantic_owner_id).where(
        SemanticGraphRegistryModel.graph_iri.in_(graph_iris),
        SemanticGraphRegistryModel.semantic_owner_type == "ontology",
    )
    owner_ids = list(session.scalars(owners))
    project_ids = list(
        session.scalars(
            select(OntologyModel.project_id).where(OntologyModel.id.in_(owner_ids)).distinct()
        )
    )
    lock_projects(session, project_ids)
    return list(
        session.scalars(
            select(OntologyModel)
            .where(OntologyModel.id.in_(owner_ids))
            .order_by(OntologyModel.id)
            .with_for_update()
        )
    )


def lock_projects(session, project_ids: list[str]):
    """Shared write boundary: Project, then Ontology, then Attempt/fence."""
    return list(
        session.scalars(
            select(ProjectModel)
            .where(ProjectModel.id.in_(sorted(set(project_ids))))
            .order_by(ProjectModel.id)
            .with_for_update()
        )
    )
