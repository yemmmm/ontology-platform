"""Graph-set export service for Turtle/TriG/JSON-LD.

TriG preserves named-graph boundaries. Turtle requires either a single graph
or an explicit merged-profile request. JSON-LD compacts with the platform
context plus projection metadata terms.
"""

from __future__ import annotations

from typing import Any, Protocol

from rdflib import Dataset, Graph

from app.core.config import Settings
from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
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
    "evidenceStatus": "projection:evidenceStatus",
    "derivedState": "projection:derivedState",
    "isStale": "projection:isStale",
}


class _VisibilityPolicy(Protocol):
    def filter_graphs(
        self, graph_iris: list[str], visibility_context: dict[str, Any] | None
    ) -> tuple[list[str], list[dict[str, str]]]: ...


class SemanticExportService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        settings: Settings | None,
        visibility_policy: _VisibilityPolicy | None = None,
    ) -> None:
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.settings = settings
        self.visibility_policy = visibility_policy

    def export(
        self,
        graph_set_id: str,
        format: str,
        include: str = "asserted",
        include_evidence: bool = False,
        include_shapes: bool = False,
        include_policy: bool = False,
        include_metadata: bool = False,
        allow_stale_derived: bool = False,
        visibility_context: dict[str, Any] | None = None,
    ) -> tuple[str, list[dict[str, str]]]:
        scope = self.scope_resolver.resolve(
            graph_set_id=graph_set_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        graph_iris = list(scope.source_graph_iris)
        if include_evidence:
            graph_iris.extend(scope.governance_graph_iris)
        if include_shapes:
            graph_iris.extend(scope.shape_graph_iris)
        if scope.reasoning_result_graph_iri and scope.derived_state.get(
            "reasoning", {}
        ).get("status") != "missing":
            graph_iris.append(scope.reasoning_result_graph_iri)
        if scope.rule_result_graph_iri and scope.derived_state.get(
            "rule", {}
        ).get("status") != "missing":
            graph_iris.append(scope.rule_result_graph_iri)

        warnings = list(scope.warnings)
        if self.visibility_policy is not None:
            graph_iris, visibility_warnings = self.visibility_policy.filter_graphs(
                graph_iris, visibility_context
            )
            warnings.extend(visibility_warnings)

        dataset = self._load_dataset(graph_iris)
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
