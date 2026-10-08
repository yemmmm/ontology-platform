from single_model_support import seed_model
from app.core.config import Settings
from app.repositories.models import SemanticProjectionManifestModel
from app.services.semantic_derived_state import SemanticRevisionService, SemanticDerivedStateService


def test_model_write_updates_owned_version_and_invalidates_only_its_index(in_memory_session):
    a = seed_model(in_memory_session, "a")
    b = seed_model(in_memory_session, "b")
    signatures = (a.source_signature, b.source_signature)
    for model in (a,b):
        in_memory_session.add(SemanticProjectionManifestModel(
            id=model.id, ontology_id=model.id, projection_kind="search", target_partition=model.id,
            source_signature=model.source_signature, status="current"))
    in_memory_session.flush()
    SemanticRevisionService(in_memory_session).bump_revisions([a.model_graph_iri])
    SemanticDerivedStateService(in_memory_session, Settings()).mark_stale_after_edit([a.model_graph_iri])
    assert a.model_revision == 1
    assert a.source_signature != signatures[0]
    assert b.source_signature == signatures[1]
    assert in_memory_session.get(SemanticProjectionManifestModel, "a").status == "stale"
    assert in_memory_session.get(SemanticProjectionManifestModel, "b").status == "current"
