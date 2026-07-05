"""Search projection document builder + writer interface.

The writer interface (``clear`` + ``write``) is the contract Phase 7 will
satisfy with a real search backend. Phase 6 ships ``FakeSearchWriter`` so
tests do not require live infrastructure.
"""

from __future__ import annotations

from typing import Any, Protocol

from rdflib import Dataset, URIRef
from rdflib.namespace import RDF, RDFS

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_projection_job import ProjectionWriter
from app.services.semantic_read_scope import ScopeResolution


class SearchWriter(Protocol):
    def clear(self, partition: str) -> None: ...
    def write(self, partition: str, documents: list[dict[str, Any]]) -> None: ...


class FakeSearchWriter:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self.partition: str | None = None

    def clear(self, partition: str) -> None:
        self.docs = []
        self.partition = partition

    def write(self, partition: str, documents: list[dict[str, Any]]) -> None:
        self.partition = partition
        self.docs.extend(documents)


class SemanticSearchProjectionService(ProjectionWriter):
    kind = "search"

    def __init__(
        self, rdf_store: RdfStoreRepository, writer: SearchWriter
    ) -> None:
        self.rdf_store = rdf_store
        self.writer = writer

    def rebuild(
        self, job_id: str, scope: ScopeResolution, partition: str
    ) -> dict[str, int]:
        dataset = self._load_dataset(scope)
        documents = self._build_documents(dataset, scope)
        self.writer.clear(partition)
        self.writer.write(partition, documents)
        return {
            "node_count": 0,
            "relationship_count": 0,
            "document_count": len(documents),
        }

    def _load_dataset(self, scope: ScopeResolution) -> Dataset:
        dataset = Dataset()
        iris = list(scope.source_graph_iris)
        if scope.reasoning_result_graph_iri:
            iris.append(scope.reasoning_result_graph_iri)
        for iri in iris:
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _build_documents(
        self, dataset: Dataset, scope: ScopeResolution
    ) -> list[dict[str, Any]]:
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
                    "id": iri,
                    "iri": iri,
                    "resource_kind": self._resource_kind(dataset, subject),
                    "label": label,
                    "text": " | ".join(text_parts),
                    "assertion_kind": self._assertion_kind(str(graph), scope),
                    "source_graph_iri": str(graph),
                    "source_signature": scope.source_signature,
                    "graph_set_id": scope.graph_set_id,
                    "evidence_status": "unknown",
                    "is_stale": is_stale,
                    "visibility_labels": [],
                }
            )
        return documents

    def _label(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj, _ in dataset.quads((subject, RDFS.label, None, None)):
            return str(obj)
        return None

    def _comment(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj, _ in dataset.quads((subject, RDFS.comment, None, None)):
            return str(obj)
        return None

    def _resource_kind(self, dataset: Dataset, subject: URIRef) -> str:
        for _, _, obj, _ in dataset.quads((subject, RDF.type, None, None)):
            return str(obj)
        return "resource"

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
