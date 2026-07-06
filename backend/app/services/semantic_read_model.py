"""Graph-derived compact business JSON read models.

Read models are compiled from versioned SPARQL templates over graph sets.
Every statement-bearing row is decorated with origin, assertion-kind,
evidence status, provenance, and staleness metadata. Phase 6 visibility
policy is optional; when supplied, rows from graphs whose label is not in
the caller's visibility context are filtered out.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_read_scope import (
    ScopeMember,
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


class _ShapeEndpointProtocol(Protocol):
    """Minimal interface SemanticShapeEndpointService satisfies."""

    def read_merged_guidance(self, graph_set_id: str, class_iri: str) -> dict[str, Any]: ...


class SemanticReadModelService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        timeout_seconds: float = 5.0,
        default_limit: int = 500,
        visibility_policy: _VisibilityPolicy | None = None,
        shape_endpoint: _ShapeEndpointProtocol | None = None,
    ) -> None:
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.timeout_seconds = timeout_seconds
        self.default_limit = default_limit
        self.visibility_policy = visibility_policy
        # shape_endpoint is injected by the API layer (which owns the SQLAlchemy
        # session); unit tests can pass a fake. When None, entity-shape raises
        # a ReadModelError at call time.
        self.shape_endpoint = shape_endpoint

    def read_model(
        self,
        graph_set_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        limit: int | None = None,
        field_set: str = "summary",
        visibility_context: dict[str, Any] | None = None,
        entity_iri: str | None = None,
        class_iri: str | None = None,
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
        if template.name == "graph-set-staleness":
            items = [self._compose_graph_set_staleness(scope, field_set)]
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
        if template.name == "entity-shape":
            items = [self._compose_entity_shape(graph_set_id, entity_iri, class_iri)]
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
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
        return self._envelope(
            template=template,
            scope=scope,
            items=items,
            warnings=warnings,
        )

    def _envelope(
        self,
        *,
        template: ReadModelTemplate,
        scope: ScopeResolution,
        items: list[dict[str, Any]],
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "graph_set_id": scope.graph_set_id,
            "source_signature": scope.source_signature,
            "projection_version": template.projection_version,
            "model_name": template.name,
            "include": scope.include,
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

    # ------------------------------------------------------------------
    # entity-shape composer (Stage 2 §5.3)
    # ------------------------------------------------------------------

    def _compose_entity_shape(
        self,
        graph_set_id: str,
        entity_iri: str | None,
        class_iri: str | None,
    ) -> dict[str, Any]:
        """Delegate to SemanticShapeEndpointService to fetch merged guidance
        for the entity's class. Caller must pass either ``class_iri`` directly,
        or ``entity_iri`` plus a resolver that we can lookup against (deferred
        to the shape endpoint service via class IRI lookup at present).
        """
        if self.shape_endpoint is None:
            raise ReadModelError(
                "entity-shape read model requires a shape endpoint service"
            )
        target = class_iri
        if target is None:
            if entity_iri is None:
                raise ReadModelError(
                    "entity-shape read model requires either class_iri or entity_iri"
                )
            raise ReadModelError(
                "entity-shape read model cannot yet resolve class_iri from "
                "entity_iri; supply class_iri explicitly"
            )
        return self.shape_endpoint.read_merged_guidance(
            graph_set_id=graph_set_id,
            class_iri=target,
        )

    # ------------------------------------------------------------------
    # graph-set-staleness composer
    # ------------------------------------------------------------------

    def _compose_graph_set_staleness(
        self, scope: ScopeResolution, field_set: str
    ) -> dict[str, Any]:
        members: list[dict[str, Any]] = []
        for member in scope.members:
            entry: dict[str, Any] = {
                "iri": member.graph_iri,
                "role": member.role,
                "editable": member.editable,
                "validation_stale": self._member_stale(member, "validation"),
                "reasoning_stale": self._member_stale(member, "reasoning"),
                "rule_stale": self._member_stale(member, "rule"),
                "last_semantic_edit_at": (
                    member.last_edit_at.isoformat() if member.last_edit_at else None
                ),
            }
            if field_set == "detail":
                entry["derived_pointers"] = self._derived_pointers_for_member(member)
            members.append(entry)
        missing = self._missing_evidence_count(scope)
        return {
            "graph_set_id": scope.graph_set_id,
            "members": members,
            "missing_evidence_count": missing,
            "last_semantic_edit_at": self._latest_member_edit_at(scope),
        }

    @staticmethod
    def _member_stale(member: ScopeMember, kind: str) -> bool | None:
        derived = member.derived_state or {}
        state = derived.get(kind)
        if not state:
            return None
        return state.get("status") == "stale"

    @staticmethod
    def _derived_pointers_for_member(member: ScopeMember) -> dict[str, Any]:
        derived = member.derived_state or {}
        out: dict[str, Any] = {}
        for kind in ("validation", "reasoning", "rule"):
            state = derived.get(kind)
            if state:
                out[kind] = {
                    "result_graph_iri": state.get("result_graph_iri"),
                    "became_current_at": (
                        state["became_current_at"].isoformat()
                        if isinstance(state.get("became_current_at"), datetime)
                        else state.get("became_current_at")
                    ),
                    "engine_name": state.get("engine_name"),
                    "engine_version": state.get("engine_version"),
                    "rule_version": state.get("rule_version"),
                    "shape_version": state.get("shape_version"),
                }
        return out

    @staticmethod
    def _latest_member_edit_at(scope: ScopeResolution) -> str | None:
        timestamps = [
            m.last_edit_at for m in scope.members if m.last_edit_at is not None
        ]
        if not timestamps:
            return None
        return max(timestamps).isoformat()

    def _missing_evidence_count(self, scope: ScopeResolution) -> int:
        template = get_template("graph-set-staleness")
        iris = [m.graph_iri for m in scope.members]
        if not iris:
            return 0
        query = template.body.replace(
            "{graph_iris}", " ".join(f"<{i}>" for i in iris)
        )
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=iris,
            timeout_seconds=self.timeout_seconds,
            limit=1,
        )
        rows = list(self._rows(result))
        if not rows:
            return 0
        cell = rows[0].get("count")
        if isinstance(cell, dict):
            return int(cell.get("value", 0))
        return int(cell)
