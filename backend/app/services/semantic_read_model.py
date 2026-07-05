"""Graph-derived compact business JSON read models.

Read models are compiled from versioned SPARQL templates over graph sets.
Every statement-bearing row is decorated with origin, assertion-kind,
evidence status, provenance, and staleness metadata. Phase 6 visibility
policy is optional; when supplied, rows from graphs whose label is not in
the caller's visibility context are filtered out.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_read_scope import (
    ScopeResolution,
    SemanticReadScopeResolver,
)
from app.services.semantic_sparql_templates import ReadModelTemplate, get_template


class ReadModelError(RuntimeError):
    status_code = 400


class _VisibilityPolicy(Protocol):
    def evaluate(
        self, graph_iri: str, visibility_context: dict[str, Any] | None
    ) -> Any: ...


class SemanticReadModelService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        timeout_seconds: float = 5.0,
        default_limit: int = 500,
        visibility_policy: _VisibilityPolicy | None = None,
    ) -> None:
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.timeout_seconds = timeout_seconds
        self.default_limit = default_limit
        self.visibility_policy = visibility_policy

    def read_model(
        self,
        graph_set_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        limit: int | None = None,
        field_set: str = "summary",
        visibility_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            template = get_template(model_name)
        except KeyError as exc:
            raise ReadModelError(f"Unknown read model: {model_name}") from exc
        scope = self.scope_resolver.resolve(
            graph_set_id=graph_set_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        graph_iris = self._graph_iris_for_scope(scope, template)
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        query = template.body.replace("{limit}", str(bounded_limit))
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=graph_iris,
            timeout_seconds=self.timeout_seconds,
            limit=bounded_limit,
        )
        items: list[dict[str, Any]] = []
        warnings = list(scope.warnings)
        for row in self._rows(result):
            decorated = self._decorate_row(row, scope, template)
            if self.visibility_policy is not None:
                decision = self.visibility_policy.evaluate(
                    decorated["source_graph_iri"], visibility_context
                )
                if not decision.allow:
                    warnings.append(
                        {
                            "code": "visibility_graph_omitted",
                            "message": (
                                f"Graph {decorated['source_graph_iri']} "
                                "omitted by visibility policy."
                            ),
                        }
                    )
                    continue
                if decision.redact_evidence:
                    decorated["evidence_ids"] = []
                    decorated["evidence_status"] = "not_applicable"
            items.append(decorated)
        return {
            "graph_set_id": scope.graph_set_id,
            "source_signature": scope.source_signature,
            "projection_version": template.projection_version,
            "include": include,
            "derived_state": scope.derived_state,
            "warnings": warnings,
            "items": items,
        }

    def _graph_iris_for_scope(
        self, scope: ScopeResolution, template: ReadModelTemplate
    ) -> list[str]:
        iris = list(scope.source_graph_iris)
        if (
            scope.include in {"asserted-plus-reasoning", "full-working-view"}
            and scope.reasoning_result_graph_iri
            and scope.reasoning_result_graph_iri not in iris
        ):
            iris.append(scope.reasoning_result_graph_iri)
        if (
            scope.include in {"asserted-plus-rules", "full-working-view"}
            and scope.rule_result_graph_iri
            and scope.rule_result_graph_iri not in iris
        ):
            iris.append(scope.rule_result_graph_iri)
        return iris

    def _rows(self, result: Any) -> list[dict[str, str]]:
        if hasattr(result, "bindings"):
            return list(result.bindings)
        result_obj = getattr(result, "result", result)
        if isinstance(result_obj, dict):
            return list(result_obj.get("results", {}).get("bindings", []))
        if hasattr(result_obj, "rows"):
            return list(result_obj.rows)
        return []

    def _decorate_row(
        self,
        row: dict[str, Any],
        scope: ScopeResolution,
        template: ReadModelTemplate,
    ) -> dict[str, Any]:
        iri = self._cell(row, "class") or self._cell(row, "entity") or self._cell(row, "subject") or self._cell(row, "iri") or ""
        label = self._cell(row, "label")
        source_graph_iri = self._cell(row, "graph")
        if not source_graph_iri:
            source_graph_iri = scope.source_graph_iris[0] if scope.source_graph_iris else ""
        return {
            "id": iri,
            "iri": iri,
            "label": label,
            "source_graph_iri": source_graph_iri,
            "assertion_kind": self._assertion_kind_for(source_graph_iri, scope, template),
            "evidence_status": template.evidence_status,
            "evidence_ids": [],
            "provenance": {
                "generated_by": None,
                "run_id": None,
                "actor": None,
                "timestamp": None,
            },
            "audit_status": "system_accepted",
            "staleness": {
                "is_stale": self._is_stale(source_graph_iri, scope),
                "reason": self._staleness_reason(source_graph_iri, scope),
            },
        }

    @staticmethod
    def _cell(row: dict[str, Any], key: str) -> str | None:
        if key not in row:
            return None
        value = row[key]
        if isinstance(value, dict):
            return value.get("value")
        if value is None:
            return None
        return str(value)

    def _assertion_kind_for(
        self,
        source_graph_iri: str,
        scope: ScopeResolution,
        template: ReadModelTemplate,
    ) -> str:
        if (
            scope.reasoning_result_graph_iri
            and source_graph_iri == scope.reasoning_result_graph_iri
        ):
            return "owl_inferred"
        if (
            scope.rule_result_graph_iri
            and source_graph_iri == scope.rule_result_graph_iri
        ):
            return "rule_derived"
        return template.assertion_kind

    def _is_stale(self, source_graph_iri: str, scope: ScopeResolution) -> bool:
        if source_graph_iri == scope.reasoning_result_graph_iri:
            return scope.derived_state.get("reasoning", {}).get("status") == "stale"
        if source_graph_iri == scope.rule_result_graph_iri:
            return scope.derived_state.get("rule", {}).get("status") == "stale"
        return False

    def _staleness_reason(
        self, source_graph_iri: str, scope: ScopeResolution
    ) -> str | None:
        if self._is_stale(source_graph_iri, scope):
            return "derived_pointer_stale"
        return None
