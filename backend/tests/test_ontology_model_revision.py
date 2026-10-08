"""R4.0-027: one Ontology revision, independent of storage/configuration hashes."""

from sqlalchemy import select

from app.core.config import Settings
from app.repositories.models import SemanticProjectionManifestModel
from app.services.modeling_workspace import OntologyModelRevisionService
from app.services.semantic_derived_state import SemanticRevisionService
from app.services.semantic_projection_job import SemanticProjectionJobService
from app.services.semantic_read_scope import SemanticReadScopeResolver
from single_model_support import seed_model


def test_revision_is_number_and_does_not_depend_on_content_hash(in_memory_session):
    ontology = seed_model(in_memory_session, "revision-model")
    service = OntologyModelRevisionService(in_memory_session, Settings())
    assert service.version_for(ontology.id) == 0
    ontology.model_content_hash = "different-content-hash"
    in_memory_session.commit()
    assert service.version_for(ontology.id) == 0


def test_committed_write_advances_ontology_revision_and_rollback_does_not(in_memory_session):
    ontology = seed_model(in_memory_session, "revision-model")
    in_memory_session.commit()
    service = SemanticRevisionService(in_memory_session)
    service.bump_revisions([ontology.model_graph_iri])
    in_memory_session.commit()
    assert ontology.model_revision == 1
    service.bump_revisions([ontology.model_graph_iri])
    in_memory_session.rollback()
    assert ontology.model_revision == 1


def test_rebuild_does_not_advance_revision(in_memory_session):
    ontology = seed_model(in_memory_session, "revision-model")

    class Writer:
        kind = "search"

        def rebuild(self, **kwargs):
            return {"document_count": 1}

    jobs = SemanticProjectionJobService(
        in_memory_session, {"search": Writer()}, SemanticReadScopeResolver
    )
    job = jobs.create_job(ontology.id, "search", "v1")
    assert job.model_revision == 0
    assert jobs.run_job(job.id).status == "succeeded"
    assert ontology.model_revision == 0


def test_model_change_during_build_cannot_promote(in_memory_session):
    ontology = seed_model(in_memory_session, "revision-model")

    class Writer:
        kind = "search"

        def rebuild(self, **kwargs):
            SemanticRevisionService(in_memory_session).bump_revisions([ontology.model_graph_iri])
            return {"document_count": 1}

    jobs = SemanticProjectionJobService(
        in_memory_session, {"search": Writer()}, SemanticReadScopeResolver
    )
    job = jobs.create_job(ontology.id, "search", "v1")
    assert jobs.run_job(job.id).status == "stale"
    assert in_memory_session.scalar(select(SemanticProjectionManifestModel)) is None
