"""R1.2-003 retrieval contracts independent of a live embedding provider."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticGraphSetModel,
    SemanticProjectionManifestModel,
    SemanticRetrievalDocumentModel,
)
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_projection_job import SemanticProjectionJobService
from app.services.semantic_retrieval import (
    RETRIEVAL_KIND,
    RetrievalConfig,
    PgVectorRetrievalRepository,
    SemanticRetrievalCoordinator,
    SemanticRetrievalProjectionService,
    SemanticResourceRetrievalService,
    fuse_context_candidates,
    mark_retrieval_stale,
    normalize_retrieval_text,
    recall_summary,
    rule_set_signature,
)
from app.services.semantic_read_scope import SemanticReadScopeResolver


class _NoopStore:
    def get_graph(self, graph_iri, format):  # noqa: ARG002
        return ""


class _NoopEmbedding:
    def embed(self, texts):  # noqa: ARG002
        raise AssertionError("Document construction must not call the provider")


class _FixedEmbedding:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def embed(self, texts):
        return [[0.25] * self.dimensions for _ in texts]


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


def test_persisted_backfill_identity_matches_public_reader_and_enters_candidate_scan(
    in_memory_session,
) -> None:
    """A promoted vector job must use the exact public reader identity tuple."""

    settings = Settings(
        semantic_graph_iri_prefix="https://retrieval-identity.test/graphs",
        embedding_dimensions=256,
    )
    in_memory_session.add(
        ProjectModel(id="project-retrieval", name="Retrieval", normalized_label="retrieval")
    )
    ontology = OntologyModel(
        id="ontology-retrieval",
        project_id="project-retrieval",
        name="Retrieval ontology",
    )
    in_memory_session.add(ontology)
    in_memory_session.flush()
    workspace_service = OntologyWorkspaceService(in_memory_session, settings)
    workspace_service.ensure(ontology)
    in_memory_session.commit()
    workspace = workspace_service.context(ontology.id)
    graph_set_id = workspace["default_graph_set_id"]
    data_graph_iri = next(
        item["graph_iri"] for item in workspace["members"] if item["role"] == "asserted_data"
    )

    class PersistentFixtureStore:
        def get_graph(self, graph_iri, _format):
            if graph_iri != data_graph_iri:
                return ""
            return f'''
                @prefix owl: <http://www.w3.org/2002/07/owl#> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                <{data_graph_iri}> {{
                  <https://example.test/CustomerSupportWorkflow>
                    a owl:Class ;
                    rdfs:label "Customer Support Workflow"@en,
                               "客户支持工作流"@zh .
                }}
            '''

    projection = SemanticRetrievalProjectionService(
        in_memory_session,
        PersistentFixtureStore(),
        _FixedEmbedding(settings.embedding_dimensions),
        settings,
    )
    jobs = SemanticProjectionJobService(
        in_memory_session,
        writers={RETRIEVAL_KIND: projection},
        scope_resolver_builder=SemanticReadScopeResolver,
    )
    job = jobs.create_job(
        graph_set_id=graph_set_id,
        projection_kind=RETRIEVAL_KIND,
        projection_version=settings.semantic_retrieval_projection_version,
    )
    job = jobs.run_job(job.id)

    document = in_memory_session.scalar(
        select(SemanticRetrievalDocumentModel).where(
            SemanticRetrievalDocumentModel.build_job_id == job.id
        )
    )
    manifest = in_memory_session.scalar(
        select(SemanticProjectionManifestModel).where(
            SemanticProjectionManifestModel.graph_set_id == graph_set_id,
            SemanticProjectionManifestModel.projection_kind == RETRIEVAL_KIND,
        )
    )
    graph_set = in_memory_session.get(SemanticGraphSetModel, graph_set_id)
    assert job.status == "succeeded"
    assert document is not None
    assert manifest is not None and manifest.status == "current"
    assert manifest.active_job_id == job.id
    assert graph_set is not None
    assert document.label == "Customer Support Workflow"
    assert document.labels == [
        {
            "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
            "value": "Customer Support Workflow",
            "language": "en",
        },
        {
            "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
            "value": "客户支持工作流",
            "language": "zh",
        },
    ]
    assert "客户支持工作流" in document.document_text

    config = RetrievalConfig.from_settings(settings)
    reader_identity = {
        "graph_set_id": graph_set_id,
        "ontology_id": ontology.id,
        "workspace_version": ModelingWorkspaceVersionService(
            in_memory_session, settings
        ).version_for(ontology.id),
        "source_signature": graph_set.source_signature,
        "rule_set_signature": rule_set_signature(in_memory_session, ontology.id),
        "projection_version": config.projection_version,
        "embedding_config_hash": config.config_hash,
        "build_job_id": manifest.active_job_id,
    }
    persisted_identity = {
        "graph_set_id": document.graph_set_id,
        "ontology_id": document.ontology_id,
        "workspace_version": document.workspace_version,
        "source_signature": document.source_signature,
        "rule_set_signature": document.rule_set_signature,
        "projection_version": document.projection_version,
        "embedding_config_hash": document.embedding_config_hash,
        "build_job_id": document.build_job_id,
    }

    assert persisted_identity == reader_identity
    assert reader_identity["workspace_version"] != graph_set.graph_set_metadata["workspace_version"]

    repository = PgVectorRetrievalRepository(in_memory_session, config)
    status = repository.index_status(
        graph_set_id=reader_identity["graph_set_id"],
        ontology_id=reader_identity["ontology_id"],
        workspace_version=reader_identity["workspace_version"],
        source_signature=reader_identity["source_signature"],
        current_rule_signature=reader_identity["rule_set_signature"],
    )
    assert status["status"] == "current"

    scanned_identity = {}

    def candidate_scan(**kwargs):
        scanned_identity.update(kwargs)
        return [
            {
                "resource_iri": document.resource_iri,
                "resource_kind": document.resource_kind,
                "assertion_kind": document.assertion_kind,
                "label": document.label,
                "labels": document.labels,
                "aliases": document.aliases,
                "descriptions": document.descriptions,
                "mapping_evidence": document.mapping_evidence,
                "rdf_types": document.rdf_types,
                "similarity": 0.99,
            }
        ]

    reader = SemanticResourceRetrievalService(
        in_memory_session,
        settings,
        embedding_client=_FixedEmbedding(settings.embedding_dimensions),
    )
    reader.repository.exact_cosine_candidates = candidate_scan
    result = reader.recall(
        scope=SimpleNamespace(
            ontologies=(
                SimpleNamespace(
                    ontology_id=ontology.id,
                    graph_set_id=graph_set_id,
                    workspace_version=reader_identity["workspace_version"],
                    source_signature=reader_identity["source_signature"],
                ),
            )
        ),
        query="客户支持工作流",
        resource_kinds={"concept"},
        search_mode="hybrid",
        limit=10,
    )

    assert scanned_identity == {
        "graph_set_id": reader_identity["graph_set_id"],
        "ontology_id": reader_identity["ontology_id"],
        "workspace_version": reader_identity["workspace_version"],
        "source_signature": reader_identity["source_signature"],
        "rule_signature": reader_identity["rule_set_signature"],
        "resource_kinds": {"concept"},
        "query_vector": [0.25] * settings.embedding_dimensions,
        "limit": 50,
    }
    assert result["completeness"] == "complete"
    assert result["indexes"][0]["status"] == "current"
    assert [item["iri"] for item in result["candidates"]] == [
        "https://example.test/CustomerSupportWorkflow"
    ]
    assert result["candidates"][0]["label"] == "客户支持工作流"
    assert result["candidates"][0]["match"]["candidate_level"] == "exact"
    assert result["candidates"][0]["match"]["reasons"] == [
        "exact_label",
        "semantic_candidate",
    ]

    scanned_identity.clear()
    entity_result = reader.recall_graph_set(
        scope=SemanticReadScopeResolver(in_memory_session).resolve(graph_set_id),
        query="客户支持工作流",
        resource_kinds={"concept"},
        search_mode="hybrid",
        limit=10,
    )

    assert scanned_identity["workspace_version"] == reader_identity["workspace_version"]
    assert entity_result["indexes"][0]["status"] == "current"
    assert [item["iri"] for item in entity_result["candidates"]] == [
        "https://example.test/CustomerSupportWorkflow"
    ]

    retry = jobs.create_job(
        graph_set_id=graph_set_id,
        projection_kind=RETRIEVAL_KIND,
        projection_version=settings.semantic_retrieval_projection_version,
    )
    retry = jobs.run_job(retry.id)
    documents = list(
        in_memory_session.scalars(
            select(SemanticRetrievalDocumentModel).where(
                SemanticRetrievalDocumentModel.resource_iri
                == "https://example.test/CustomerSupportWorkflow"
            )
        )
    )
    current_manifest = in_memory_session.scalar(
        select(SemanticProjectionManifestModel).where(
            SemanticProjectionManifestModel.graph_set_id == graph_set_id,
            SemanticProjectionManifestModel.projection_kind == RETRIEVAL_KIND,
            SemanticProjectionManifestModel.status == "current",
        )
    )
    assert retry.status == "succeeded"
    assert len(documents) == 2
    assert {item.build_job_id for item in documents} == {job.id, retry.id}
    assert len({item.id for item in documents}) == 2
    assert len({item.target_partition for item in documents}) == 2
    assert current_manifest is not None
    assert current_manifest.active_job_id == retry.id
    assert manifest.status == "stale"


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


def test_rebuild_failure_keeps_prior_retrieval_manifest_stale(
    in_memory_session, monkeypatch
) -> None:
    """A failed rebuild cannot make a pre-write vector partition look current."""

    in_memory_session.add(
        SemanticGraphSetModel(
            id="set-rebuild",
            name="Ontology workspace",
            scope_type="ontology",
            scope_id="ontology-rebuild",
            is_default=True,
            source_signature="source-v1",
            graph_set_metadata={"workspace_version": "workspace-v1"},
        )
    )
    in_memory_session.add(
        SemanticProjectionManifestModel(
            id="manifest-rebuild",
            graph_set_id="set-rebuild",
            projection_kind="vector",
            active_job_id="job-before-write",
            source_signature="source-v1",
            projection_version="semantic-retrieval-v1",
            target_partition="set-rebuild/vector/before-write",
            status="current",
        )
    )
    in_memory_session.commit()

    class FailingProjectionJobs:
        def __init__(self, **_kwargs):
            pass

        def create_job(self, **_kwargs):
            raise RuntimeError("embedding provider unavailable")

    monkeypatch.setattr(
        "app.services.semantic_retrieval.SemanticProjectionJobService", FailingProjectionJobs
    )
    result = SemanticRetrievalCoordinator(
        in_memory_session, _NoopStore(), Settings()
    ).rebuild_ontology("ontology-rebuild")

    assert result["write_applied"] is True
    assert result["status"] == "failed"
    assert result["stale_manifest_ids"] == ["manifest-rebuild"]
    assert in_memory_session.get(SemanticProjectionManifestModel, "manifest-rebuild").status == "stale"
