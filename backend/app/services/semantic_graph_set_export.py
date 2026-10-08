"""Graph-set export service for Turtle/TriG/JSON-LD.

TriG preserves named-graph boundaries. Turtle requires either a single graph
or an explicit merged-profile request. JSON-LD compacts with the platform
context plus projection metadata terms.
"""

from __future__ import annotations

from typing import Any

from rdflib import Dataset, Graph

from app.core.config import Settings
from app.repositories.rdf_store import RdfFormat, RdfStoreError, RdfStoreRepository
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_export import jsonld_context
from app.services.semantic_read_scope import (
    ScopeResolution,
    SemanticReadScopeResolver,
)


class ExportError(RuntimeError):
    status_code = 400


_PROJECTION_TERMS = {
    "projection": "http://ontology-platform.local/semantic/vocab/projection/",
    "assertionKind": "projection:assertionKind",
    "sourceGraph": "projection:sourceGraph",
    "derivedState": "projection:derivedState",
    "isStale": "projection:isStale",
}


class SemanticExportService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        settings: Settings | None,
        access_view: SemanticAccessView | None = None,
    ) -> None:
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.settings = settings
        self.access_view = access_view or SemanticAccessView.all_visible()

    def export(
        self,
        graph_set_id: str,
        format: str,
        include: str = "asserted",
        include_policy: bool = False,
        include_metadata: bool = False,
        allow_stale_derived: bool = False,
    ) -> tuple[str, list[dict[str, str]]]:
        scope = self.scope_resolver.resolve(
            graph_set_id=graph_set_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        graph_iris = list(scope.source_graph_iris)
        warnings = list(scope.warnings)

        dataset = self._load_dataset(graph_iris)
        # R3.0-004: drop quads whose s/p/o names an unauthorized protected
        # member, including evidence attachment graphs, without warnings.
        self.access_view.filter_quads(dataset)
        payload = self._serialize(
            dataset,
            format,
            scope,
            merged_fallback=include == "full-working-view",
        )
        return payload, warnings

    def _load_dataset(self, graph_iris: list[str]) -> Dataset:
        dataset = Dataset()
        for iri in graph_iris:
            # A graph named by the scope but not yet present in the store
            # (for example a workspace whose data graph has no statements
            # yet) exports as an empty graph instead of failing the whole
            # request: Oxigraph answers GET /store?graph= with 404, which
            # the repository surfaces as RdfStoreUnavailable.
            if hasattr(self.rdf_store, "graph_exists"):
                try:
                    if not self.rdf_store.graph_exists(iri):
                        continue
                except RdfStoreError:
                    pass  # fall through; get_graph reports the real error
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _serialize(
        self,
        dataset: Dataset,
        format: str,
        scope: ScopeResolution,
        merged_fallback: bool,
    ) -> str:
        if format == "trig":
            return dataset.serialize(format="trig")
        if format == "turtle":
            non_empty = [
                g
                for g in dataset.graphs()
                if len(g) > 0 and str(g.identifier) != "urn:x-rdflib:default"
            ]
            if len(non_empty) > 1 and not merged_fallback:
                raise ExportError(
                    "Turtle export requires either a single graph or an explicit merged-view profile."
                )
            merged = Graph()
            for graph in non_empty:
                for triple in graph:
                    merged.add(triple)
            return merged.serialize(format="turtle")
        if format == "json-ld":
            context = self._build_context()
            return dataset.serialize(format="json-ld", context=context, indent=2)
        raise ExportError(f"Unsupported export format: {format}")

    def _build_context(self) -> dict[str, Any]:
        if self.settings is None:
            base_context: dict[str, Any] = {"@version": 1.1}
        else:
            base_context = jsonld_context(self.settings)
        return {**base_context, **_PROJECTION_TERMS}
