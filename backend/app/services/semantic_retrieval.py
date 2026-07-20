"""Scoped, rebuildable pgvector retrieval for public semantic read paths.

The module deliberately owns projection configuration, document construction,
exact-vector filtering and fusion.  It never writes RDF, Rules, aliases, or
query text: vector rows are a disposable projection of current metadata.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterable

from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF, RDFS
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticGraphSetModel,
    SemanticGraphSetMemberModel,
    SemanticProjectionManifestModel,
    SemanticRetrievalDocumentModel,
    SemanticMappingModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
)
from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.embedding import EmbeddingClient, EmbeddingServiceError
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.semantic_projection_job import SemanticProjectionJobService
from app.services.semantic_read_scope import ScopeResolution
from app.services.semantic_read_scope import SemanticReadScopeResolver


SKOS_ALT_LABEL = "http://www.w3.org/2004/02/skos/core#altLabel"
DCTERMS_DESCRIPTION = "http://purl.org/dc/terms/description"
RETRIEVAL_KIND = "vector"
EXACT_EVIDENCE_REASONS = {"exact_label", "exact_alias", "exact_mapping", "identifier"}


class SemanticRetrievalError(RuntimeError):
    """A safe, non-provider-specific retrieval failure."""


@dataclass(frozen=True)
class RetrievalConfig:
    projection_version: str
    model: str
    dimensions: int
    document_template_version: str
    normalization_version: str
    fusion_version: str
    min_similarity: float
    ambiguity_margin: float
    provider_identity: str
    query_timeout_seconds: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "RetrievalConfig":
        return cls(
            projection_version=settings.semantic_retrieval_projection_version,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            document_template_version=settings.semantic_retrieval_document_template_version,
            normalization_version=settings.semantic_retrieval_normalization_version,
            fusion_version=settings.semantic_retrieval_fusion_version,
            min_similarity=settings.semantic_retrieval_min_similarity,
            ambiguity_margin=settings.semantic_retrieval_ambiguity_margin,
            provider_identity=_provider_identity(settings.embedding_base_url),
            query_timeout_seconds=settings.semantic_retrieval_query_timeout_seconds,
        )

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "provider": self.provider_identity,
                    "model": self.model,
                    "dimensions": self.dimensions,
                    "document_template": self.document_template_version,
                    "normalization": self.normalization_version,
                    "threshold": self.min_similarity,
                    "margin": self.ambiguity_margin,
                    "fusion": self.fusion_version,
                    "projection": self.projection_version,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def _provider_identity(value: str) -> str:
    """Keep only a non-secret provider identity in the config contract."""
    return re.sub(r"//[^/@]+@", "//", (value or "").rstrip("/")).casefold()


def normalize_retrieval_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return " ".join(value.replace("_", " ").replace("-", " ").casefold().split())


def rule_set_signature(session: Session, ontology_id: str) -> str:
    """Hash exactly the active Rule fields that can appear in a document."""
    rows = session.execute(
        select(SemanticRuleModel, SemanticRuleDefinitionModel)
        .join(
            SemanticRuleDefinitionModel,
            SemanticRuleDefinitionModel.id == SemanticRuleModel.current_definition_id,
        )
        .where(
            SemanticRuleModel.ontology_id == ontology_id,
            SemanticRuleModel.status == "active",
            SemanticRuleDefinitionModel.status == "active",
        )
        .order_by(SemanticRuleModel.id, SemanticRuleDefinitionModel.id)
    )
    payload = [
        {
            "rule_id": rule.id,
            "rule_iri": rule.rule_iri,
            "definition_id": definition.id,
            "name": definition.name,
            "language": definition.language,
            "version": definition.version,
            "metadata": definition.rule_metadata or {},
        }
        for rule, definition in rows
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def retrieval_workspace_version(session: Session, settings: Settings, ontology_id: str) -> str:
    """Use the public read contract's authoritative workspace version.

    Retrieval documents are only queryable when their identity tuple agrees
    with the public Context and Entity readers.  Graph-set metadata contains
    setup-era annotations (including the initial ``r001-v1`` marker), not the
    current graph-and-Rule version fence.
    """
    return ModelingWorkspaceVersionService(session, settings).version_for(ontology_id)


def mark_retrieval_stale(session: Session, ontology_id: str) -> list[str]:
    """Invalidate all retrieval manifests in the caller's SQL transaction."""
    graph_set_ids = list(
        session.scalars(
            select(SemanticGraphSetModel.id).where(
                SemanticGraphSetModel.scope_type == "ontology",
                SemanticGraphSetModel.scope_id == ontology_id,
            )
        )
    )
    if not graph_set_ids:
        return []
    rows = list(
        session.scalars(
            select(SemanticProjectionManifestModel).where(
                SemanticProjectionManifestModel.graph_set_id.in_(graph_set_ids),
                SemanticProjectionManifestModel.projection_kind == RETRIEVAL_KIND,
                SemanticProjectionManifestModel.status == "current",
            )
        )
    )
    for row in rows:
        row.status = "stale"
    session.flush()
    return [row.id for row in rows]


class PgVectorRetrievalRepository:
    """PostgreSQL projection store. Every vector query is scope-filtered first."""

    def __init__(self, session: Session, config: RetrievalConfig) -> None:
        self.session = session
        self.config = config

    def clear_partition(self, target_partition: str) -> None:
        self.session.execute(
            delete(SemanticRetrievalDocumentModel).where(
                SemanticRetrievalDocumentModel.target_partition == target_partition
            )
        )
        self.session.flush()

    def write_documents(self, documents: Iterable[dict[str, Any]]) -> None:
        self.session.add_all(SemanticRetrievalDocumentModel(**item) for item in documents)
        self.session.flush()

    def index_status(
        self,
        *,
        graph_set_id: str,
        ontology_id: str,
        workspace_version: str,
        source_signature: str,
        current_rule_signature: str,
    ) -> dict[str, Any]:
        manifests = list(
            self.session.scalars(
                select(SemanticProjectionManifestModel).where(
                    SemanticProjectionManifestModel.graph_set_id == graph_set_id,
                    SemanticProjectionManifestModel.projection_kind == RETRIEVAL_KIND,
                )
            )
        )
        common = {
            "ontology_id": ontology_id,
            "workspace_version": workspace_version,
            "projection_version": self.config.projection_version,
            "embedding_model": self.config.model,
            "embedding_config_hash": self.config.config_hash,
            "ambiguity_margin": self.config.ambiguity_margin,
        }
        if not manifests:
            return {**common, "status": "missing"}
        current = [item for item in manifests if item.status == "current"]
        if not current:
            return {**common, "status": "stale"}
        if not any(
            item.source_signature == source_signature
            and item.projection_version == self.config.projection_version
            for item in current
        ):
            return {**common, "status": "stale"}
        exists = self.session.scalar(
            select(SemanticRetrievalDocumentModel.id).where(
                SemanticRetrievalDocumentModel.graph_set_id == graph_set_id,
                SemanticRetrievalDocumentModel.ontology_id == ontology_id,
                SemanticRetrievalDocumentModel.workspace_version == workspace_version,
                SemanticRetrievalDocumentModel.source_signature == source_signature,
                SemanticRetrievalDocumentModel.rule_set_signature == current_rule_signature,
                SemanticRetrievalDocumentModel.projection_version == self.config.projection_version,
                SemanticRetrievalDocumentModel.embedding_config_hash == self.config.config_hash,
                SemanticRetrievalDocumentModel.build_job_id.in_(
                    [item.active_job_id for item in current if item.active_job_id]
                ),
            ).limit(1)
        )
        if exists is None:
            return {**common, "status": "config_mismatch"}
        return {**common, "status": "current"}

    def exact_cosine_candidates(
        self,
        *,
        graph_set_id: str,
        ontology_id: str,
        workspace_version: str,
        source_signature: str,
        rule_signature: str,
        resource_kinds: set[str],
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not resource_kinds:
            return []
        # The WHERE predicate is deliberately before ORDER/LIMIT.  This is an
        # exact pgvector cosine scan; no HNSW/IVFFlat index is created in v1.
        # ``SET LOCAL`` is transaction-scoped, so a timeout can only degrade
        # this request and can never leak to another session/request.
        timeout_ms = max(1, int(self.config.query_timeout_seconds * 1000))
        self.session.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
        result = self.session.execute(
            text(
                """
                SELECT d.resource_iri, d.resource_kind, d.assertion_kind, d.label,
                       d.labels, d.aliases, d.descriptions, d.mapping_evidence, d.rdf_types,
                       1 - (d.embedding <=> CAST(:query_vector AS vector)) AS similarity
                  FROM semantic_retrieval_documents AS d
                  JOIN semantic_projection_manifests AS m
                    ON m.active_job_id = d.build_job_id
                 WHERE d.graph_set_id = :graph_set_id
                   AND d.ontology_id = :ontology_id
                   AND d.workspace_version = :workspace_version
                   AND d.source_signature = :source_signature
                   AND d.rule_set_signature = :rule_signature
                   AND d.projection_version = :projection_version
                   AND d.embedding_config_hash = :config_hash
                   AND d.resource_kind = ANY(:resource_kinds)
                   AND m.graph_set_id = :graph_set_id
                   AND m.projection_kind = :projection_kind
                   AND m.status = 'current'
                   AND m.source_signature = :source_signature
                   AND m.projection_version = :projection_version
                 ORDER BY d.embedding <=> CAST(:query_vector AS vector), d.resource_iri
                 LIMIT :limit
                """
            ),
            {
                "graph_set_id": graph_set_id,
                "ontology_id": ontology_id,
                "workspace_version": workspace_version,
                "source_signature": source_signature,
                "rule_signature": rule_signature,
                "projection_version": self.config.projection_version,
                "config_hash": self.config.config_hash,
                "projection_kind": RETRIEVAL_KIND,
                "resource_kinds": sorted(resource_kinds),
                "query_vector": _vector_literal(query_vector),
                "limit": limit,
            },
        )
        return [dict(row) for row in result.mappings()]


class SemanticRetrievalProjectionService:
    """Build immutable job partitions from allow-listed RDF and Rule metadata."""

    kind = RETRIEVAL_KIND

    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        embedding_client: EmbeddingClient,
        settings: Settings,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.embedding_client = embedding_client
        self.settings = settings
        self.config = RetrievalConfig.from_settings(settings)
        self.repository = PgVectorRetrievalRepository(session, self.config)

    def rebuild(self, job_id: str, scope: ScopeResolution, partition: str) -> dict[str, int]:
        graph_set = self.session.get(SemanticGraphSetModel, scope.graph_set_id)
        if graph_set is None or graph_set.scope_type != "ontology" or not graph_set.scope_id:
            raise SemanticRetrievalError("Retrieval projection requires an Ontology-scoped workspace")
        ontology_id = graph_set.scope_id
        try:
            workspace_version = retrieval_workspace_version(
                self.session, self.settings, ontology_id
            )
        except LookupError as exc:
            raise SemanticRetrievalError("Retrieval projection requires a workspace version") from exc
        documents = self._metadata_documents(
            ontology_id=ontology_id,
            graph_set_id=scope.graph_set_id,
            workspace_version=workspace_version,
            source_signature=scope.source_signature,
            rule_signature=rule_set_signature(self.session, ontology_id),
            job_id=job_id,
            partition=partition,
            scope=scope,
        )
        self._embed_documents(documents)
        self.repository.clear_partition(partition)
        self.repository.write_documents(documents)
        return {"node_count": 0, "relationship_count": 0, "document_count": len(documents)}

    def _metadata_documents(
        self,
        *,
        ontology_id: str,
        graph_set_id: str,
        workspace_version: str,
        source_signature: str,
        rule_signature: str,
        job_id: str,
        partition: str,
        scope: ScopeResolution,
    ) -> list[dict[str, Any]]:
        dataset = Dataset()
        for graph_iri in scope.source_graph_iris:
            content = self.rdf_store.get_graph(graph_iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        metadata: dict[str, dict[str, Any]] = {}
        for subject, predicate, obj, _graph in dataset.quads((None, None, None, None)):
            if not isinstance(subject, URIRef):
                continue
            record = metadata.setdefault(
                str(subject),
                {"iri": str(subject), "labels": [], "aliases": [], "descriptions": [], "types": []},
            )
            predicate_iri = str(predicate)
            if predicate == RDF.type and isinstance(obj, URIRef):
                record["types"].append(str(obj))
            elif predicate_iri == str(RDFS.label) and isinstance(obj, Literal):
                record["labels"].append(_evidence(predicate_iri, obj))
            elif predicate_iri == SKOS_ALT_LABEL and isinstance(obj, Literal):
                record["aliases"].append(_evidence(predicate_iri, obj))
            elif predicate_iri in {str(RDFS.comment), DCTERMS_DESCRIPTION} and isinstance(obj, Literal):
                record["descriptions"].append(_evidence(predicate_iri, obj))
        mappings = self._mappings_by_resource(ontology_id)
        documents = [
            self._document_from_metadata(
                value,
                mappings=mappings.get(value["iri"], []),
                ontology_id=ontology_id,
                graph_set_id=graph_set_id,
                workspace_version=workspace_version,
                source_signature=source_signature,
                rule_signature=rule_signature,
                job_id=job_id,
                partition=partition,
            )
            for _, value in sorted(metadata.items())
        ]
        documents.extend(
            self._rule_documents(
                ontology_id=ontology_id,
                graph_set_id=graph_set_id,
                workspace_version=workspace_version,
                source_signature=source_signature,
                rule_signature=rule_signature,
                job_id=job_id,
                partition=partition,
            )
        )
        return [item for item in documents if item is not None]

    def _mappings_by_resource(self, ontology_id: str) -> dict[str, list[dict[str, str]]]:
        """Project only governed mapping identifiers and field names.

        Mapping records are an explicit semantic source.  The projection keeps
        their stable ID, target type, external field local name, and join-key
        *names* only; arbitrary data-source values never enter embedding text.
        """
        values: dict[str, list[dict[str, str]]] = {}
        rows = self.session.scalars(
            select(SemanticMappingModel).where(
                SemanticMappingModel.ontology_id == ontology_id,
                SemanticMappingModel.status == "active",
            )
        )
        for row in rows:
            join_names = _mapping_join_key_names(row.join_key or {})
            evidence = {
                "mapping_id": row.id,
                "target_type": row.target_type,
                "external_field": _local_name(row.external_field_name),
                "join_keys": ", ".join(join_names),
            }
            values.setdefault(row.target_id, []).append(evidence)
        return {
            resource_iri: sorted(
                records,
                key=lambda item: (
                    item["mapping_id"], item["external_field"], item["join_keys"]
                ),
            )
            for resource_iri, records in values.items()
        }

    def _document_from_metadata(
        self, value: dict[str, Any], *, mappings: list[dict[str, str]], **identity: Any
    ) -> dict[str, Any] | None:
        rdf_types = sorted(set(value["types"]))
        resource_kind = _resource_kind(rdf_types)
        if resource_kind is None:
            return None
        labels = _sorted_evidence(value["labels"])
        aliases = _sorted_evidence(value["aliases"])
        descriptions = _sorted_evidence(value["descriptions"])
        label = labels[0]["value"] if labels else _local_name(value["iri"])
        document_text = _document_text(
            iri=value["iri"],
            label=label,
            labels=labels,
            aliases=aliases,
            descriptions=descriptions,
            rdf_types=rdf_types,
            mappings=mappings,
        )
        return _document_record(
            resource_iri=value["iri"],
            resource_kind=resource_kind,
            label=label,
            labels=labels,
            aliases=aliases,
            descriptions=descriptions,
            mapping_evidence=mappings,
            rdf_types=rdf_types,
            document_text=document_text,
            config=self.config,
            **identity,
        )

    def _rule_documents(self, *, ontology_id: str, **identity: Any) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(SemanticRuleModel, SemanticRuleDefinitionModel)
            .join(
                SemanticRuleDefinitionModel,
                SemanticRuleDefinitionModel.id == SemanticRuleModel.current_definition_id,
            )
            .where(
                SemanticRuleModel.ontology_id == ontology_id,
                SemanticRuleModel.status == "active",
                SemanticRuleDefinitionModel.status == "active",
            )
            .order_by(SemanticRuleModel.rule_iri)
        )
        result = []
        for rule, definition in rows:
            descriptions = []
            raw_description = (definition.rule_metadata or {}).get("description")
            if isinstance(raw_description, str) and raw_description.strip():
                descriptions = [{"predicate": DCTERMS_DESCRIPTION, "value": raw_description.strip(), "language": ""}]
            document_text = _document_text(
                iri=rule.rule_iri,
                label=definition.name,
                labels=[],
                aliases=[],
                descriptions=descriptions,
                rdf_types=[definition.language, definition.output_kind],
                mappings=[],
            )
            result.append(
                _document_record(
                    resource_iri=rule.rule_iri,
                    resource_kind="rule",
                    label=definition.name,
                    labels=[],
                    aliases=[],
                    descriptions=descriptions,
                    mapping_evidence=[],
                    rdf_types=[definition.language, definition.output_kind],
                    document_text=document_text,
                    config=self.config,
                    ontology_id=ontology_id,
                    **identity,
                )
            )
        return result

    def _embed_documents(self, documents: list[dict[str, Any]]) -> None:
        reusable = {
            row.text_hash: list(row.embedding)
            for row in self.session.scalars(
                select(SemanticRetrievalDocumentModel).where(
                    SemanticRetrievalDocumentModel.embedding_config_hash == self.config.config_hash
                )
            )
        }
        pending = [item for item in documents if item["text_hash"] not in reusable]
        for item in documents:
            if item["text_hash"] in reusable:
                item["embedding"] = reusable[item["text_hash"]]
        batch_size = self.settings.semantic_retrieval_build_batch_size
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset : offset + batch_size]
            vectors = self.embedding_client.embed([item["document_text"] for item in batch])
            if len(vectors) != len(batch):
                raise SemanticRetrievalError("Embedding provider returned an invalid document count")
            for item, vector in zip(batch, vectors, strict=True):
                _validate_vector(vector, self.config.dimensions)
                item["embedding"] = vector


class SemanticRetrievalCoordinator:
    """Run the disposable retrieval rebuild only after authoritative writes commit.

    RDF, Rule, and PostgreSQL write paths share this coordinator so they agree
    on the one observable contract: the semantic write remains applied when an
    embedding/provider rebuild fails, and the caller receives a stable index
    state instead of a fake cross-store rollback.
    """

    def __init__(self, session: Session, rdf_store: RdfStoreRepository, settings: Settings):
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings

    def rebuild_ontology(self, ontology_id: str) -> dict[str, Any]:
        # Persist invalidation in its own transaction. A later provider/job
        # failure must never roll this back and leave an old vector partition
        # queryable as though it reflected the just-committed RDF/Rule fact.
        try:
            stale_manifest_ids = mark_retrieval_stale(self.session, ontology_id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            return {
                "ontology_id": ontology_id,
                "write_applied": True,
                "status": "failed",
                "warning": "retrieval_index_failed",
            }
        graph_set = self.session.scalar(
            select(SemanticGraphSetModel).where(
                SemanticGraphSetModel.scope_type == "ontology",
                SemanticGraphSetModel.scope_id == ontology_id,
                SemanticGraphSetModel.is_default.is_(True),
            )
        )
        if graph_set is None:
            return {
                "ontology_id": ontology_id,
                "write_applied": True,
                "status": "stale",
                "warning": "retrieval_index_missing",
                "stale_manifest_ids": stale_manifest_ids,
            }
        service = SemanticProjectionJobService(
            session=self.session,
            writers={
                RETRIEVAL_KIND: SemanticRetrievalProjectionService(
                    self.session,
                    self.rdf_store,
                    EmbeddingClient(self.settings),
                    self.settings,
                )
            },
            scope_resolver_builder=SemanticReadScopeResolver,
        )
        try:
            job = service.create_job(
                graph_set_id=graph_set.id,
                projection_kind=RETRIEVAL_KIND,
                projection_version=self.settings.semantic_retrieval_projection_version,
            )
            job = service.run_job(job.id)
            return {
                "ontology_id": ontology_id,
                "write_applied": True,
                "status": "current" if job.status == "succeeded" else job.status,
                "job_id": job.id,
                "workspace_version": (graph_set.graph_set_metadata or {}).get(
                    "workspace_version"
                ),
                "projection_version": self.settings.semantic_retrieval_projection_version,
                "stale_manifest_ids": stale_manifest_ids,
            }
        except Exception:
            # Deliberately do not expose provider errors, query text, or
            # credentials.  The already-committed semantic write is still
            # authoritative and readers will fall back to lexical recall.
            self.session.rollback()
            return {
                "ontology_id": ontology_id,
                "write_applied": True,
                "status": "failed",
                "warning": "retrieval_index_failed",
                "stale_manifest_ids": stale_manifest_ids,
            }

    def rebuild_affected(
        self,
        *,
        affected_graph_iris: Iterable[str] = (),
        ontology_ids: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        ids = {value for value in ontology_ids if value}
        graph_iris = sorted(set(affected_graph_iris))
        if graph_iris:
            try:
                ids.update(
                    self.session.scalars(
                        select(SemanticGraphSetModel.scope_id)
                        .join(
                            SemanticGraphSetMemberModel,
                            SemanticGraphSetMemberModel.graph_set_id
                            == SemanticGraphSetModel.id,
                        )
                        .where(
                            SemanticGraphSetModel.scope_type == "ontology",
                            SemanticGraphSetModel.scope_id.is_not(None),
                            SemanticGraphSetMemberModel.graph_iri.in_(graph_iris),
                        )
                    )
                )
            except Exception:
                self.session.rollback()
                return [
                    {
                        "ontology_id": ontology_id,
                        "write_applied": True,
                        "status": "failed",
                        "warning": "retrieval_index_failed",
                    }
                    for ontology_id in sorted(ids)
                ]
        return [self.rebuild_ontology(ontology_id) for ontology_id in sorted(ids)]


class SemanticResourceRetrievalService:
    """Perform one request-scoped embedding and pre-filtered exact cosine scans."""

    def __init__(self, session: Session, settings: Settings, embedding_client: EmbeddingClient | None = None):
        self.session = session
        self.settings = settings
        self.config = RetrievalConfig.from_settings(settings)
        self.embedding_client = embedding_client or EmbeddingClient(settings)
        self.repository = PgVectorRetrievalRepository(session, self.config)

    def recall(
        self,
        *,
        scope: Any,
        query: str,
        resource_kinds: set[str],
        search_mode: str,
        limit: int,
    ) -> dict[str, Any]:
        if search_mode not in {"hybrid", "lexical"}:
            raise SemanticRetrievalError("search_mode must be hybrid or lexical")
        signatures = {item.ontology_id: rule_set_signature(self.session, item.ontology_id) for item in scope.ontologies}
        indexes = [
            self.repository.index_status(
                graph_set_id=item.graph_set_id,
                ontology_id=item.ontology_id,
                workspace_version=item.workspace_version,
                source_signature=item.source_signature,
                current_rule_signature=signatures[item.ontology_id],
            )
            for item in scope.ontologies
        ]
        if search_mode == "lexical":
            return {"candidates": [], "indexes": indexes, "warnings": [], "completeness": "complete"}
        unavailable = [item for item in indexes if item["status"] != "current"]
        warnings = [_index_warning(item["status"]) for item in unavailable]
        if not any(item["status"] == "current" for item in indexes):
            return {
                "candidates": [],
                "indexes": indexes,
                "warnings": warnings,
                "completeness": "degraded",
            }
        try:
            vector = self.embedding_client.embed([query])[0]
            _validate_vector(vector, self.config.dimensions)
        except (EmbeddingServiceError, IndexError, TypeError, ValueError):
            return {
                "candidates": [],
                "indexes": indexes,
                "warnings": [*warnings, {"code": "semantic_recall_degraded", "message": "Vector recall is unavailable."}],
                "completeness": "degraded",
            }
        candidates: list[dict[str, Any]] = []
        per_ontology_limit = min(200, max(50, limit * 5))
        try:
            for ontology in scope.ontologies:
                if next(item for item in indexes if item["ontology_id"] == ontology.ontology_id)["status"] != "current":
                    continue
                rows = self.repository.exact_cosine_candidates(
                    graph_set_id=ontology.graph_set_id,
                    ontology_id=ontology.ontology_id,
                    workspace_version=ontology.workspace_version,
                    source_signature=ontology.source_signature,
                    rule_signature=signatures[ontology.ontology_id],
                    resource_kinds=resource_kinds,
                    query_vector=vector,
                    limit=per_ontology_limit,
                )
                candidates.extend(
                    _semantic_candidate(row, ontology.ontology_id, self.config.min_similarity)
                    for row in rows
                    if float(row["similarity"]) >= self.config.min_similarity
                )
        except Exception:
            return {
                "candidates": [],
                "indexes": indexes,
                "warnings": [*warnings, {"code": "semantic_recall_degraded", "message": "Vector recall is unavailable."}],
                "completeness": "degraded",
            }
        promote_exact_label_candidates(candidates, query)
        return {
            "candidates": candidates,
            "indexes": indexes,
            "warnings": warnings,
            "completeness": "degraded" if unavailable else "complete",
        }

    def recall_multi(
        self,
        *,
        scope: Any,
        queries: list[str],
        resource_kinds: set[str],
        search_mode: str,
        limit: int,
    ) -> dict[str, Any]:
        """Run one bounded embedding batch for multiple related expressions.

        Reuses the same scope, manifest fences, and degradation rules as
        ``recall``. Expressions are embedded in a single provider call;
        exact-vector scans then run per expression inside the resolved scope.
        The returned ``candidates_by_query`` preserves input order, including
        duplicates. ``completeness`` aggregates per-expression degradation so
        R1.2-004 fusion can still surface available evidence.
        """
        if search_mode not in {"hybrid", "lexical"}:
            raise SemanticRetrievalError("search_mode must be hybrid or lexical")
        signatures = {
            item.ontology_id: rule_set_signature(self.session, item.ontology_id)
            for item in scope.ontologies
        }
        indexes = [
            self.repository.index_status(
                graph_set_id=item.graph_set_id,
                ontology_id=item.ontology_id,
                workspace_version=item.workspace_version,
                source_signature=item.source_signature,
                current_rule_signature=signatures[item.ontology_id],
            )
            for item in scope.ontologies
        ]
        if search_mode == "lexical" or not queries:
            return {
                "candidates_by_query": [[] for _ in queries],
                "indexes": indexes,
                "warnings": [],
                "completeness": "complete",
            }
        unavailable = [item for item in indexes if item["status"] != "current"]
        warnings = [_index_warning(item["status"]) for item in unavailable]
        if not any(item["status"] == "current" for item in indexes):
            return {
                "candidates_by_query": [[] for _ in queries],
                "indexes": indexes,
                "warnings": warnings,
                "completeness": "degraded",
            }
        try:
            vectors = self.embedding_client.embed(list(queries))
            if len(vectors) != len(queries):
                raise SemanticRetrievalError(
                    "Embedding provider returned an invalid document count"
                )
            for vector in vectors:
                _validate_vector(vector, self.config.dimensions)
        except (EmbeddingServiceError, IndexError, TypeError, ValueError):
            return {
                "candidates_by_query": [[] for _ in queries],
                "indexes": indexes,
                "warnings": [
                    *warnings,
                    {"code": "semantic_recall_degraded", "message": "Vector recall is unavailable."},
                ],
                "completeness": "degraded",
            }
        per_ontology_limit = min(200, max(50, limit * 5))
        candidates_by_query: list[list[dict[str, Any]]] = []
        any_complete = False
        try:
            for vector in vectors:
                per_expression: list[dict[str, Any]] = []
                for ontology in scope.ontologies:
                    status = next(
                        item for item in indexes if item["ontology_id"] == ontology.ontology_id
                    )["status"]
                    if status != "current":
                        continue
                    rows = self.repository.exact_cosine_candidates(
                        graph_set_id=ontology.graph_set_id,
                        ontology_id=ontology.ontology_id,
                        workspace_version=ontology.workspace_version,
                        source_signature=ontology.source_signature,
                        rule_signature=signatures[ontology.ontology_id],
                        resource_kinds=resource_kinds,
                        query_vector=vector,
                        limit=per_ontology_limit,
                    )
                    per_expression.extend(
                        _semantic_candidate(row, ontology.ontology_id, self.config.min_similarity)
                        for row in rows
                        if float(row["similarity"]) >= self.config.min_similarity
                    )
                candidates_by_query.append(per_expression)
                if per_expression:
                    any_complete = True
        except Exception:
            return {
                "candidates_by_query": [[] for _ in queries],
                "indexes": indexes,
                "warnings": [
                    *warnings,
                    {"code": "semantic_recall_degraded", "message": "Vector recall is unavailable."},
                ],
                "completeness": "degraded",
            }
        if any_complete:
            completeness = "degraded" if unavailable else "complete"
        else:
            completeness = "degraded"
        return {
            "candidates_by_query": candidates_by_query,
            "indexes": indexes,
            "warnings": warnings,
            "completeness": completeness,
        }

    def recall_graph_set(
        self,
        *,
        scope: ScopeResolution,
        query: str,
        resource_kinds: set[str],
        search_mode: str,
        limit: int,
    ) -> dict[str, Any]:
        graph_set = self.session.get(SemanticGraphSetModel, scope.graph_set_id)
        if graph_set is None or graph_set.scope_type != "ontology" or not graph_set.scope_id:
            return {
                "candidates": [],
                "indexes": [],
                "warnings": [
                    {"code": "semantic_recall_degraded", "message": "Vector recall is unavailable."}
                ],
                "completeness": "degraded",
            }
        try:
            workspace_version = retrieval_workspace_version(
                self.session, self.settings, graph_set.scope_id
            )
        except LookupError:
            return {
                "candidates": [],
                "indexes": [],
                "warnings": [
                    {"code": "semantic_recall_degraded", "message": "Vector recall is unavailable."}
                ],
                "completeness": "degraded",
            }
        ontology = SimpleNamespace(
            ontology_id=graph_set.scope_id,
            graph_set_id=scope.graph_set_id,
            workspace_version=workspace_version,
            source_signature=scope.source_signature,
        )
        return self.recall(
            scope=SimpleNamespace(ontologies=(ontology,)),
            query=query,
            resource_kinds=resource_kinds,
            search_mode=search_mode,
            limit=limit,
        )


def fuse_context_candidates(
    lexical: list[dict[str, Any]], semantic: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fuse scoped lexical, governed-mapping, and semantic candidates by identity."""
    by_key = {(item["ontology_id"], item["id"]): item for item in lexical}
    for item in lexical:
        _normalise_match(item, semantic_similarity=None)
        _merge_mapping_evidence(item, item)
    for item in semantic:
        key = (item["ontology_id"], item["id"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
            if not _is_semantic_candidate(item):
                _normalise_match(item, semantic_similarity=None)
            _merge_mapping_evidence(item, item)
            continue
        if _is_semantic_candidate(item):
            _normalise_match(
                existing,
                semantic_similarity=item["match"].get("semantic_similarity"),
            )
        else:
            _merge_lexical_match(existing, item)
        _merge_mapping_evidence(existing, item)
    return list(by_key.values())


def promote_exact_label_candidates(
    candidates: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    """Recover asserted-label exactness from a scoped retrieval candidate.

    The lexical SPARQL corpus remains the primary source of exact evidence.
    This guard covers an incomplete lexical scan without expanding its scope:
    it only promotes a candidate which has already passed the same current
    graph-set/manifest fences as semantic recall, and only when one of its
    persisted asserted ``rdfs:label`` evidence values equals the normalized
    user query. Callers run this before fusion so exact evidence is never
    reconstructed from a fused semantic row.
    """
    normalized_query = normalize_retrieval_text(query)
    if not normalized_query:
        return candidates
    for item in candidates:
        matching_label = _matching_asserted_label(item, normalized_query)
        if matching_label is None:
            continue
        item["label"] = matching_label
        match = item.get("match")
        if not isinstance(match, dict):
            continue
        reasons = set(match.get("reasons") or [])
        reasons.add("exact_label")
        match["reasons"] = sorted(reasons)
        match["matched_fields"] = sorted(
            set(match.get("matched_fields") or []) | {"label"}
        )
        match["matched_terms"] = sorted(
            set(match.get("matched_terms") or []) | {normalized_query}
        )
        match["lexical_score"] = max(int(match.get("lexical_score", 0) or 0), 1000)
        _normalise_match(item, semantic_similarity=match.get("semantic_similarity"))
    return candidates


def _matching_asserted_label(item: dict[str, Any], normalized_query: str) -> str | None:
    """Return the exact asserted-label value without trusting display-label choice."""
    evidence = [
        value
        for source in (item.get("labels"), (item.get("data") or {}).get("label_evidence"))
        for value in (source or [])
        if isinstance(value, dict)
    ]
    for value in evidence:
        if value.get("predicate") != str(RDFS.label):
            continue
        raw = value.get("value")
        if isinstance(raw, str) and normalize_retrieval_text(raw) == normalized_query:
            return raw
    # Documents created before label evidence was added retain their primary
    # asserted label only.  The migration materialises it as evidence, while
    # this fallback keeps a current in-process candidate backwards compatible.
    display_label = item.get("label")
    if isinstance(display_label, str) and normalize_retrieval_text(display_label) == normalized_query:
        return display_label
    return None


def governed_mapping_lexical_candidates(
    session: Session | None,
    *,
    ontology_ids: Iterable[str],
    query: str,
    resource_kinds: set[str],
) -> list[dict[str, Any]]:
    """Return exact matches from active, scope-bound Mapping evidence only.

    Mapping values are governed PostgreSQL metadata, not a vector side effect.
    The query is deliberately equality-only across an allow-list of structural
    fields, and every candidate carries the same safe evidence payload stored
    in the retrieval projection.  That makes an external field name usable as
    a deterministic lexical anchor without joining to another Ontology.
    """
    scoped_ontology_ids = sorted({value for value in ontology_ids if value})
    normalized_query = normalize_retrieval_text(query)
    if session is None or not scoped_ontology_ids or not normalized_query:
        return []
    rows = session.scalars(
        select(SemanticMappingModel)
        .where(
            SemanticMappingModel.ontology_id.in_(scoped_ontology_ids),
            SemanticMappingModel.status == "active",
        )
        .order_by(
            SemanticMappingModel.ontology_id,
            SemanticMappingModel.target_id,
            SemanticMappingModel.id,
        )
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        kind = _mapping_target_kind(row.target_type)
        if kind not in resource_kinds:
            continue
        evidence = _mapping_evidence(row)
        matching_fields = {
            "mapping_id": evidence["mapping_id"],
            "mapping_external_field": evidence["external_field"],
            "mapping_join_key": evidence["join_keys"],
            "mapping_target_type": evidence["target_type"],
        }
        matched_fields = sorted(
            field
            for field, value in matching_fields.items()
            if normalize_retrieval_text(value) == normalized_query
        )
        if not matched_fields:
            continue
        candidates.append(
            {
                "id": row.target_id,
                "kind": kind,
                "ontology_id": row.ontology_id,
                "iri": row.target_id,
                "label": _local_name(row.target_id),
                "aliases": [],
                "description": None,
                "data": {"rdf_types": [], "mapping_evidence": [evidence]},
                "mapping_evidence": [evidence],
                "distance": 0,
                "assertion_kind": "asserted",
                "match": {
                    "score": 900,
                    "lexical_score": 900,
                    "semantic_similarity": None,
                    "effective_score": 0.9,
                    "candidate_level": "exact",
                    "method": "mapping",
                    "matched_terms": [normalized_query],
                    "matched_fields": matched_fields,
                    "reasons": ["exact_mapping"],
                },
            }
        )
    return candidates


def _is_semantic_candidate(item: dict[str, Any]) -> bool:
    match = item.get("match") or {}
    return (
        match.get("candidate_level") == "semantic_candidate"
        or "semantic_candidate" in set(match.get("reasons") or [])
    )


def _merge_lexical_match(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge exact governed evidence without discarding an existing vector score."""
    match = existing["match"]
    incoming_match = incoming["match"]
    match["lexical_score"] = max(
        int(match.get("lexical_score", match.get("score", 0)) or 0),
        int(incoming_match.get("lexical_score", incoming_match.get("score", 0)) or 0),
    )
    match["reasons"] = sorted(
        set(match.get("reasons") or []) | set(incoming_match.get("reasons") or [])
    )
    match["matched_fields"] = sorted(
        set(match.get("matched_fields") or []) | set(incoming_match.get("matched_fields") or [])
    )
    match["matched_terms"] = sorted(
        set(match.get("matched_terms") or []) | set(incoming_match.get("matched_terms") or [])
    )
    _normalise_match(existing, semantic_similarity=match.get("semantic_similarity"))


def _merge_mapping_evidence(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    records = [
        item
        for source in (existing, incoming)
        for item in [
            *(source.get("mapping_evidence") or []),
            *((source.get("data") or {}).get("mapping_evidence") or []),
        ]
        if isinstance(item, dict)
    ]
    if not records:
        return
    unique = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")): item
        for item in records
    }
    evidence = [unique[key] for key in sorted(unique)]
    existing["mapping_evidence"] = evidence
    existing.setdefault("data", {})["mapping_evidence"] = evidence


def _normalise_match(item: dict[str, Any], semantic_similarity: float | None) -> None:
    match = item["match"]
    lexical_score = int(match.get("lexical_score", match.get("score", 0)) or 0)
    similarity = semantic_similarity if semantic_similarity is not None else match.get("semantic_similarity")
    semantic_rank = int(round(float(similarity) * 1000)) if similarity is not None else 0
    score = max(lexical_score, semantic_rank)
    match["score"] = score
    match["lexical_score"] = lexical_score
    match["semantic_similarity"] = round(float(similarity), 3) if similarity is not None else None
    match["effective_score"] = round(score / 1000, 3)
    reasons = set(match.get("reasons") or [])
    exact = bool(reasons & EXACT_EVIDENCE_REASONS)
    match["candidate_level"] = "exact" if exact else "lexical_candidate"
    match["method"] = "mixed" if similarity is not None else _method_for_reasons(reasons)


def recall_summary(candidates: list[dict[str, Any]], retrieval: dict[str, Any], mode: str) -> dict[str, Any]:
    levels = [item.get("match", {}).get("candidate_level") for item in candidates]
    stable_ids = {f"{item['ontology_id']}:{item['id']}" for item in candidates if item.get("match", {}).get("candidate_level") == "exact"}
    ranked = sorted(
        (item.get("match", {}).get("effective_score", 0.0) for item in candidates), reverse=True
    )
    ambiguous = len(stable_ids) > 1 or (
        not stable_ids
        and len(ranked) > 1
        and ranked[0] - ranked[1] <= _configured_ambiguity_margin(retrieval)
    )
    if ambiguous:
        status = "ambiguous"
    elif "exact" in levels:
        status = "exact"
    elif candidates:
        status = "candidate"
    else:
        status = "no_match"
    return {
        "mode": mode,
        "match_status": status,
        "completeness": retrieval["completeness"],
        "indexes": retrieval["indexes"],
    }


def _semantic_candidate(row: dict[str, Any], ontology_id: str, threshold: float) -> dict[str, Any]:
    similarity = round(float(row["similarity"]), 3)
    score = int(round(similarity * 1000))
    mapping_evidence = _sanitise_mapping_evidence(row.get("mapping_evidence") or [])
    labels = _sanitise_label_evidence(
        row.get("labels") or [], row.get("label"), row.get("resource_kind")
    )
    return {
        "id": row["resource_iri"],
        "kind": row["resource_kind"],
        "ontology_id": ontology_id,
        "iri": row["resource_iri"],
        "label": row.get("label") or _local_name(row["resource_iri"]),
        "labels": labels,
        "aliases": [item.get("value", "") for item in row.get("aliases") or []],
        "description": next((item.get("value") for item in row.get("descriptions") or []), None),
        "data": {
            "rdf_types": row.get("rdf_types") or [],
            "mapping_evidence": mapping_evidence,
            "label_evidence": labels,
        },
        "mapping_evidence": mapping_evidence,
        "distance": 0,
        "assertion_kind": row.get("assertion_kind") or "asserted",
        "match": {
            "score": score,
            "lexical_score": 0,
            "semantic_similarity": similarity,
            "effective_score": round(score / 1000, 3),
            "candidate_level": "semantic_candidate",
            "method": "semantic",
            "matched_terms": [],
            "matched_fields": [],
            "reasons": ["semantic_candidate"],
            "threshold": threshold,
        },
    }


def _document_record(*, resource_iri: str, resource_kind: str, label: str, labels: list[dict[str, str]], aliases: list[dict[str, str]], descriptions: list[dict[str, str]], mapping_evidence: list[dict[str, str]], rdf_types: list[str], document_text: str, config: RetrievalConfig, **identity: Any) -> dict[str, Any]:
    text_hash = hashlib.sha256(document_text.encode("utf-8")).hexdigest()
    document_id = hashlib.sha256(
        "|".join(
            (
                identity["graph_set_id"],
                identity["workspace_version"],
                identity["source_signature"],
                identity["rule_signature"],
                resource_iri,
                resource_kind,
                config.projection_version,
                config.config_hash,
                identity["job_id"],
                identity["partition"],
            )
        ).encode("utf-8")
    ).hexdigest()
    return {
        "id": document_id,
        "resource_iri": resource_iri,
        "resource_kind": resource_kind,
        "assertion_kind": "asserted",
        "label": label,
        "labels": labels,
        "aliases": aliases,
        "descriptions": descriptions,
        "mapping_evidence": mapping_evidence,
        "rdf_types": sorted(set(rdf_types)),
        "normalized_text": normalize_retrieval_text(document_text),
        "document_text": document_text,
        "text_hash": text_hash,
        "embedding": [],
        "embedding_model": config.model,
        "embedding_config_hash": config.config_hash,
        "projection_version": config.projection_version,
        "visibility": [],
        "ontology_id": identity["ontology_id"],
        "graph_set_id": identity["graph_set_id"],
        "workspace_version": identity["workspace_version"],
        "source_signature": identity["source_signature"],
        "rule_set_signature": identity["rule_signature"],
        "build_job_id": identity["job_id"],
        "target_partition": identity["partition"],
    }


def _document_text(
    *,
    iri: str,
    label: str,
    labels: list[dict[str, str]],
    aliases: list[dict[str, str]],
    descriptions: list[dict[str, str]],
    rdf_types: list[str],
    mappings: list[dict[str, str]],
) -> str:
    fields = [
        ("label", label),
        ("labels", ", ".join(item["value"] for item in labels)),
        ("aliases", ", ".join(item["value"] for item in aliases)),
        ("description", " ".join(item["value"] for item in descriptions)),
        ("identifier", _local_name(iri)),
        ("types", ", ".join(_local_name(item) for item in sorted(set(rdf_types)))),
        (
            "mappings",
            "; ".join(
                " ".join(
                    value
                    for value in (
                        mapping.get("external_field"),
                        mapping.get("join_keys"),
                        mapping.get("target_type"),
                        mapping.get("mapping_id"),
                    )
                    if value
                )
                for mapping in mappings
            ),
        ),
    ]
    return "\n".join(f"{name}: {value}" for name, value in fields if value)[:12000]


def _resource_kind(rdf_types: list[str]) -> str | None:
    lowered = " ".join(rdf_types).casefold()
    if "class" in lowered:
        return "concept"
    if "property" in lowered:
        return "relation"
    if "operation" in lowered:
        return "operation"
    if rdf_types:
        return "instance"
    return None


def _evidence(predicate: str, value: Literal) -> dict[str, str]:
    return {"predicate": predicate, "value": str(value), "language": value.language or ""}


def _sorted_evidence(values: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"predicate": predicate, "value": value, "language": language}
        for predicate, value, language in sorted(
            {(x["predicate"], x["value"], x["language"]) for x in values}
        )
    ]


def _sanitise_label_evidence(
    values: list[Any], fallback: Any, resource_kind: Any
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict) or value.get("predicate") != str(RDFS.label):
            continue
        label = value.get("value")
        if not isinstance(label, str) or not label.strip():
            continue
        language = value.get("language")
        records.append(
            {
                "predicate": str(RDFS.label),
                "value": label,
                "language": language if isinstance(language, str) else "",
            }
        )
    if not records and resource_kind != "rule" and isinstance(fallback, str) and fallback.strip():
        records.append(
            {"predicate": str(RDFS.label), "value": fallback, "language": ""}
        )
    return _sorted_evidence(records)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{item:.9g}" for item in vector) + "]"


def _validate_vector(vector: list[float], dimensions: int) -> None:
    if len(vector) != dimensions or any(not isinstance(item, (int, float)) or not math.isfinite(item) for item in vector):
        raise SemanticRetrievalError("Embedding provider returned an invalid vector")


def _index_warning(status: str) -> dict[str, str]:
    code = f"vector_index_{status}" if status in {"missing", "stale", "failed", "config_mismatch"} else "semantic_recall_degraded"
    return {"code": code, "message": "Semantic vector recall is unavailable for one Ontology."}


def _method_for_reasons(reasons: set[str]) -> str:
    if "exact_label" in reasons:
        return "label"
    if "exact_alias" in reasons:
        return "alt_label"
    if "exact_mapping" in reasons:
        return "mapping"
    if "identifier" in reasons:
        return "identifier"
    return "description"


def _local_name(value: str) -> str:
    return re.split(r"[/#: ]", value.rstrip("/#: "))[-1] or value


def _mapping_join_key_names(value: Any) -> list[str]:
    """Keep structural key names while excluding mapped data values."""
    if isinstance(value, dict):
        names = []
        for key, nested in sorted(value.items()):
            names.append(str(key))
            names.extend(_mapping_join_key_names(nested))
        return sorted(set(names))
    if isinstance(value, list):
        return sorted({name for item in value for name in _mapping_join_key_names(item)})
    return []


def _mapping_target_kind(target_type: str) -> str:
    return {
        "class": "concept",
        "concept": "concept",
        "property": "relation",
        "relation_type": "relation",
        "relation": "relation",
        "entity": "instance",
        "instance": "instance",
        "rule": "rule",
        "operation": "operation",
    }.get(target_type, "instance")


def _mapping_evidence(row: SemanticMappingModel) -> dict[str, str]:
    return {
        "mapping_id": row.id,
        "target_type": row.target_type,
        "external_field": _local_name(row.external_field_name),
        "join_keys": ", ".join(_mapping_join_key_names(row.join_key or {})),
    }


def _sanitise_mapping_evidence(values: list[Any]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        mapping_id = value.get("mapping_id")
        target_type = value.get("target_type")
        external_field = value.get("external_field")
        join_keys = value.get("join_keys")
        if not all(isinstance(item, str) for item in (mapping_id, target_type, external_field)):
            continue
        records.append(
            {
                "mapping_id": mapping_id,
                "target_type": target_type,
                "external_field": external_field,
                "join_keys": join_keys if isinstance(join_keys, str) else "",
            }
        )
    unique = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")): item
        for item in records
    }
    return [unique[key] for key in sorted(unique)]


def _configured_ambiguity_margin(retrieval: dict[str, Any]) -> float:
    indexes = retrieval.get("indexes") or []
    for index in indexes:
        try:
            return float(index.get("ambiguity_margin"))
        except (TypeError, ValueError):
            continue
    return 0.03
