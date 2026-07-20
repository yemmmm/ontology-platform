"""R1.2-003 retrieval contracts independent of a live embedding provider."""

from __future__ import annotations

from app.core.config import Settings
from app.repositories.models import SemanticGraphSetModel, SemanticProjectionManifestModel
from app.services.semantic_retrieval import (
    RetrievalConfig,
    PgVectorRetrievalRepository,
    SemanticRetrievalProjectionService,
    fuse_context_candidates,
    mark_retrieval_stale,
    normalize_retrieval_text,
    recall_summary,
)


class _NoopStore:
    def get_graph(self, graph_iri, format):  # noqa: ARG002
        return ""


class _NoopEmbedding:
    def embed(self, texts):  # noqa: ARG002
        raise AssertionError("Document construction must not call the provider")


def test_retrieval_config_hash_includes_versioned_threshold_and_provider_identity() -> None:
    baseline = RetrievalConfig.from_settings(
        Settings(embedding_base_url="https://key:secret@example.test/v1")
    )
    changed = RetrievalConfig.from_settings(
        Settings(
            embedding_base_url="https://different@example.test/v1",
            semantic_retrieval_min_similarity=0.5,
        )
    )

    assert baseline.config_hash != changed.config_hash
    assert "secret" not in baseline.provider_identity
    assert normalize_retrieval_text("Publish_Workflow-v2") == "publish workflow v2"


def test_metadata_document_allow_list_keeps_mapping_key_names_not_values(in_memory_session) -> None:
    service = SemanticRetrievalProjectionService(
        in_memory_session, _NoopStore(), _NoopEmbedding(), Settings()
    )
    document = service._document_from_metadata(
        {
            "iri": "https://example.test/CustomerWorkflow",
            "labels": [
                {
                    "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
                    "value": "Customer workflow",
                    "language": "en",
                }
            ],
            "aliases": [],
            "descriptions": [],
            "types": ["http://www.w3.org/2002/07/owl#Class"],
        },
        mappings=[
            {
                "mapping_id": "mapping-1",
                "target_type": "class",
                "external_field": "customer_id",
                "join_keys": "customer_id, workflow_key",
            }
        ],
        ontology_id="ontology-1",
        graph_set_id="set-1",
        workspace_version="workspace-v1",
        source_signature="source-v1",
        rule_signature="rules-v1",
        job_id="job-1",
        partition="set-1/vector/semantic-retrieval-v1/job-1",
    )

    assert document is not None
    assert document["resource_kind"] == "concept"
    assert document["mapping_evidence"][0]["mapping_id"] == "mapping-1"
    assert "customer_id" in document["document_text"]
    assert "Evidence" not in document["document_text"]
    assert "secret" not in document["document_text"].casefold()


def test_fusion_preserves_exact_lexical_evidence_and_exposes_candidate_summary() -> None:
    lexical = [
        {
            "id": "https://example.test/Workflow",
            "ontology_id": "ontology-1",
            "kind": "concept",
            "match": {
                "score": 1000,
                "reasons": ["exact_label"],
                "matched_fields": ["label"],
                "matched_terms": ["workflow"],
            },
        }
    ]
    semantic = [
        {
            "id": "https://example.test/Workflow",
            "ontology_id": "ontology-1",
            "kind": "concept",
            "match": {"semantic_similarity": 0.91, "reasons": ["semantic_candidate"]},
        }
    ]
    fused = fuse_context_candidates(lexical, semantic)

    assert fused[0]["match"]["candidate_level"] == "exact"
    assert fused[0]["match"]["method"] == "mixed"
    assert fused[0]["match"]["semantic_similarity"] == 0.91
    summary = recall_summary(
        fused,
        {
            "completeness": "complete",
            "indexes": [{"ambiguity_margin": 0.03}],
        },
        "hybrid",
    )
    assert summary == {
        "mode": "hybrid",
        "match_status": "exact",
        "completeness": "complete",
        "indexes": [{"ambiguity_margin": 0.03}],
    }


def test_exact_scan_uses_transaction_scoped_timeout_before_vector_query() -> None:
    class _Result:
        def mappings(self):
            return []

    class _RecordingSession:
        def __init__(self) -> None:
            self.calls = []

        def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))
            return _Result()

    session = _RecordingSession()
    config = RetrievalConfig.from_settings(Settings(semantic_retrieval_query_timeout_seconds=1.5))
    rows = PgVectorRetrievalRepository(session, config).exact_cosine_candidates(
        graph_set_id="set-1",
        ontology_id="ontology-1",
        workspace_version="workspace-v1",
        source_signature="source-v1",
        rule_signature="rules-v1",
        resource_kinds={"concept"},
        query_vector=[1.0] * config.dimensions,
        limit=5,
    )

    assert rows == []
    assert session.calls[0] == ("SET LOCAL statement_timeout = 1500", None)
    assert "WHERE d.graph_set_id" in session.calls[1][0]
    assert "ORDER BY d.embedding <=>" in session.calls[1][0]


def test_rule_transaction_marks_current_retrieval_manifests_stale(in_memory_session) -> None:
    in_memory_session.add(
        SemanticGraphSetModel(
            id="set-1",
            name="Ontology workspace",
            scope_type="ontology",
            scope_id="ontology-1",
            source_signature="source-v1",
        )
    )
    in_memory_session.add(
        SemanticProjectionManifestModel(
            id="manifest-1",
            graph_set_id="set-1",
            projection_kind="vector",
            active_job_id="job-1",
            source_signature="source-v1",
            projection_version="semantic-retrieval-v1",
            target_partition="set-1/vector/semantic-retrieval-v1/job-1",
            status="current",
        )
    )
    in_memory_session.commit()

    assert mark_retrieval_stale(in_memory_session, "ontology-1") == ["manifest-1"]
    assert in_memory_session.get(SemanticProjectionManifestModel, "manifest-1").status == "stale"
