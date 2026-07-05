"""Vector projection document builder with deterministic ids and config hashes.

Document ids are deterministic per ``(graph_set_id, iri, section_kind,
projection_version)``. The embedding config hash changes when model or
version changes, which forces manifest staleness under Phase 6 reconcile
when the embedding provider or model is updated.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from rdflib import Dataset, URIRef
from rdflib.namespace import RDF, RDFS

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_projection_job import ProjectionWriter
from app.services.semantic_read_scope import ScopeResolution


class VectorWriter(Protocol):
    def clear(self, partition: str) -> None: ...
    def write(self, partition: str, documents: list[dict[str, Any]]) -> None: ...


class FakeVectorWriter:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def clear(self, partition: str) -> None:
        self.docs = []

    def write(self, partition: str, documents: list[dict[str, Any]]) -> None:
        self.docs.extend(documents)


class SemanticVectorProjectionService(ProjectionWriter):
    kind = "vector"

    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        writer: VectorWriter,
        embedding_config: dict[str, Any] | None = None,
    ) -> None:
        self.rdf_store = rdf_store
        self.writer = writer
        self.embedding_config = embedding_config or {"model": "default", "version": "v1"}

    def rebuild(
        self, job_id: str, scope: ScopeResolution, partition: str
    ) -> dict[str, int]:
        dataset = self._load_dataset(scope)
        version = partition.rsplit("/", 1)[-1]
        documents = self._build_documents(dataset, scope, version)
        self.writer.clear(partition)
        self.writer.write(partition, documents)
        return {
            "node_count": 0,
            "relationship_count": 0,
            "document_count": len(documents),
        }

    def _load_dataset(self, scope: ScopeResolution) -> Dataset:
        dataset = Dataset()
        for iri in scope.source_graph_iris:
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _build_documents(
        self,
        dataset: Dataset,
        scope: ScopeResolution,
        version: str,
    ) -> list[dict[str, Any]]:
        config_hash = self._config_hash()
        is_stale = any(
            scope.derived_state.get(kind, {}).get("status") == "stale"
            for kind in ("reasoning", "rule")
        )
        documents: list[dict[str, Any]] = []
        seen: set[str] = set()
        for subject, _, _, graph in dataset.quads((None, None, None, None)):
            if not isinstance(subject, URIRef):
                continue
            iri = str(subject)
            if iri in seen:
                continue
            seen.add(iri)
            label = self._label(dataset, subject)
            comment = self._comment(dataset, subject)
            text_parts = [part for part in (label, comment) if part]
            documents.append(
                {
                    "id": self._deterministic_id(scope.graph_set_id, iri, version),
                    "iri": iri,
                    "text": " | ".join(text_parts),
                    "source_graph_iris": [str(graph)],
                    "embedding_config_hash": config_hash,
                    "embedding_config": dict(self.embedding_config),
                    "source_signature": scope.source_signature,
                    "graph_set_id": scope.graph_set_id,
                    "assertion_kind": self._assertion_kind(str(graph), scope),
                    "is_stale": is_stale,
                    "visibility_labels": [],
                }
            )
        return documents

    def _deterministic_id(
        self, graph_set_id: str, iri: str, version: str
    ) -> str:
        return hashlib.sha256(
            f"{graph_set_id}|{iri}|resource|{version}".encode()
        ).hexdigest()

    def _config_hash(self) -> str:
        serialised = "|".join(
            f"{k}={self.embedding_config.get(k)}"
            for k in sorted(self.embedding_config)
        )
        return hashlib.sha256(serialised.encode()).hexdigest()

    def _label(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj, _ in dataset.quads((subject, RDFS.label, None, None)):
            return str(obj)
        return None

    def _comment(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj, _ in dataset.quads((subject, RDFS.comment, None, None)):
            return str(obj)
        return None

    def _assertion_kind(self, graph_iri: str, scope: ScopeResolution) -> str:
        if (
            scope.reasoning_result_graph_iri
            and graph_iri == scope.reasoning_result_graph_iri
        ):
            return "owl_inferred"
        if (
            scope.rule_result_graph_iri
            and graph_iri == scope.rule_result_graph_iri
        ):
            return "rule_derived"
        return "asserted"
