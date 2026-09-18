"""The source Project of a checkpoint fork remains readable evidence."""

from sqlalchemy import select

from app.repositories.models import OntologyModel, SemanticGraphRegistryModel

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
    return list(
        session.scalars(
            select(OntologyModel)
            .where(OntologyModel.id.in_(owners))
            .order_by(OntologyModel.id)
            .with_for_update()
        )
    )
