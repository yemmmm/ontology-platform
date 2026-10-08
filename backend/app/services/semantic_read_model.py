"""Graph-derived compact business JSON read models.

Read models are compiled from versioned SPARQL templates over Ontology models.
Every statement-bearing row is decorated with origin, assertion-kind, and
staleness metadata. An optional ``SemanticAccessView`` (R3.0-004) filters
rows that reference unauthorized protected members before pagination,
counting, or truncation.
"""

from __future__ import annotations

import ast
import hashlib
import json
from typing import Any

from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreRepository
from app.services.operation_semantics import (
    OperationValidationError, operation_vocabulary, validate_operation_payload,
)
from app.services.fact_id import canonical_object_term, compute_fact_id
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_read_scope import (
    ScopeResolution,
    SemanticReadScopeResolver,
)
from app.services.semantic_sparql_templates import OP_VOCAB_PREFIX, ReadModelTemplate, get_template
from app.services.semantic_retrieval import (
    SemanticResourceRetrievalService,
    fuse_context_candidates,
    governed_mapping_lexical_candidates,
    normalize_retrieval_text,
    promote_exact_label_candidates,
    recall_summary,
)


class ReadModelError(RuntimeError):
    status_code = 400


# When row-level access filtering is active, templates over-fetch beyond the
# caller's bounded limit so filtering happens before pagination; the caller's
# limit is applied to the authorized subset afterwards.
_FILTERED_FETCH_LIMIT = 10_000

# R3.0-009: head room for read models that post-process rows before pagination
# (entity-list class aggregation, property-list domain filtering).
_ROW_POST_PROCESS_FETCH_MULTIPLIER = 8
_ROW_POST_PROCESS_FETCH_FLOOR = 200


_READ_MODEL_FIELD_ALIASES = {
    "class": "class_iri",
    "range": "range_iri",
    "type": "type_iri",
}

# Variables already decorated into the top-level shape by
# ``_graph_display_fields``; ``detail_variables`` passthrough skips them so
# whitelist decoration stays byte-identical for every existing template.
_READ_MODEL_WHITELIST_VARIABLES = frozenset(
    {
        "semantic_id",
        "parent",
        "class",
        "class_semantic_id",
        "class_label",
        "source",
        "target",
        "relation",
        "range",
        "type",
        "subject",
        "predicate",
        "object",
        "label",
        "graph",
    }
)


class SemanticReadModelService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        timeout_seconds: float = 5.0,
        default_limit: int = 500,
        access_view: SemanticAccessView | None = None,
        session: Any = None,
        retrieval_service: SemanticResourceRetrievalService | None = None,
    ) -> None:
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.timeout_seconds = timeout_seconds
        self.default_limit = default_limit
        self.access_view = access_view or SemanticAccessView.all_visible()
        # Publication composers use the request-scoped session.
        self.session = session
        self.retrieval_service = retrieval_service

    def read_model(
        self,
        ontology_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        limit: int | None = None,
        field_set: str = "summary",
        entity_iri: str | None = None,
        class_iri: str | None = None,
        kind: str | None = None,
        target: str | None = None,
        q: str | None = None,
        search_mode: str = "hybrid",
    ) -> dict[str, Any]:
        if field_set == "evidence":
            raise ReadModelError("field_set=evidence is no longer supported")
        try:
            template = get_template(model_name)
        except KeyError as exc:
            raise ReadModelError(f"Unknown read model: {model_name}") from exc
        if template.name == "resource-relations" and include != "asserted":
            raise ReadModelError("resource-relations requires include=asserted")
        scope = self.scope_resolver.resolve(
            ontology_id=ontology_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        graph_iris = self._graph_iris_for_scope(scope, template)
        if template.name == "resource-relations":
            return self._compose_resource_relations(
                template, scope, min(limit or template.default_limit, template.default_limit)
            )
        if template.name == "resource-list":
            # Reuse each family's authorization and nested-reference checks;
            # never merge raw RDF before filtering or infer a business role.
            bounded_limit = min(limit or template.default_limit, template.default_limit)
            by_iri: dict[str, dict[str, Any]] = {}
            warnings = list(scope.warnings)
            incomplete = False
            for family in (
                "entity-list", "ontology-schema-summary", "property-list", "relation-type-list",
                "table-mapping-list", "join-mapping-list", "enum-meaning-list", "metric-list",
                "operation-list",
            ):
                envelope = self.read_model(
                    ontology_id=ontology_id, model_name=family, include=include,
                    allow_stale_derived=allow_stale_derived, limit=bounded_limit,
                    field_set=field_set,
                )
                warnings.extend(envelope.get("warnings", []))
                incomplete |= not envelope.get("paging", {}).get("complete", True)
                for item in envelope["items"]:
                    if entity_iri and item["iri"] != entity_iri:
                        continue
                    if q and q.casefold() not in str(item.get("label") or item["iri"]).casefold():
                        continue
                    if item["iri"] in by_iri:
                        existing = by_iri[item["iri"]]
                        existing["detail_fields"] = {
                            **existing.get("detail_fields", {}), **item.get("detail_fields", {})
                        }
                    else:
                        by_iri[item["iri"]] = dict(item)
            items = sorted(by_iri.values(), key=lambda item: (item.get("label") or "", item["iri"]))
            return self._envelope(
                template=template, scope=scope, items=items[:bounded_limit], warnings=warnings,
                paging=self._paging_state(
                    limit=bounded_limit, returned=min(len(items), bounded_limit),
                    visible_count=len(items), ceiling_reached=incomplete,
                ),
            )
        if template.name == "publication-readiness":
            items = [self._compose_publication_readiness(scope, field_set)]
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
        if template.name == "fact-audit-queue":
            items, warnings = self._compose_fact_audit_queue(scope, kind, field_set)
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=warnings,
            )
        if template.name == "entity-literal-facts":
            items = self._compose_entity_literal_facts(
                template,
                scope,
                entity_iri,
                limit or template.default_limit,
            )
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
        if template.name == "entity-search":
            items, retrieval = self._compose_entity_search(
                template,
                scope,
                q=q,
                class_iri=class_iri,
                limit=limit or template.default_limit,
                field_set=field_set,
                search_mode=search_mode,
            )
            envelope = self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=[*scope.warnings, *retrieval.get("warnings", [])],
            )
            envelope["recall"] = recall_summary(items, retrieval, search_mode)
            return envelope
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        if not graph_iris and "{graph_iris}" in template.body:
            return self._envelope(
                template=template,
                scope=scope,
                items=[],
                warnings=list(scope.warnings)
                + [
                    {
                        "code": "read_model_no_model",
                        "message": (
                            f"No source graphs are available for read model "
                            f"{template.name}."
                        ),
                    }
                ],
            )
        # R3.0-009: entity-list collapses one row per (entity, class) pair into
        # one item per entity and property-list post-filters declared domains,
        # so both need fetch head room before the caller-visible pagination.
        post_processed = template.name == "entity-list" or (
            template.name == "property-list" and bool(class_iri)
        )
        fetch_limit = (
            self._expanded_fetch_limit(bounded_limit)
            if post_processed
            else self._fetch_limit(bounded_limit)
        )
        query = self._compile_template_query(
            template,
            graph_iris,
            fetch_limit,
            entity_iri=entity_iri,
        )
        if template.name in {"operation-list", "operation-detail"}:
            settings = getattr(self.scope_resolver, "settings", None) or Settings()
            query = query.replace(OP_VOCAB_PREFIX, operation_vocabulary(settings)["id"][:-2])
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=graph_iris,
            timeout_seconds=self.timeout_seconds,
            limit=fetch_limit,
        )
        items: list[dict[str, Any]] = []
        warnings = list(scope.warnings)
        rows = self._rows(result)
        # R3.0-009 §6.2: the ceiling being reached means the authorized
        # visible set itself may extend past what this projection saw.
        ceiling_reached = len(rows) >= fetch_limit
        if post_processed and ceiling_reached:
            warnings.append(
                {
                    "code": "read_model_rows_truncated",
                    "message": (
                        f"Read model {template.name} reached its fetch limit "
                        f"before aggregation/filtering; this page may be "
                        f"incomplete."
                    ),
                }
            )
        for row in rows:
            decorated = self._decorate_row(row, scope, template)
            if template.name in {"operation-list", "operation-detail"}:
                if not self.access_view.filter_items([decorated]):
                    continue
                try:
                    operation = validate_operation_payload(
                        {"operation_iri": decorated["iri"], "name": decorated.get("label"),
                         **decorated.get("detail_fields", {})},
                        settings=getattr(self.scope_resolver, "settings", None) or Settings(),
                    )
                except (OperationValidationError, ValueError, TypeError):
                    # Invalid or secret-bearing external capability data never
                    # becomes a second unchecked read surface.
                    continue
                decorated["detail_fields"] = operation
            items.append(decorated)
        if template.name == "entity-list":
            # R3.0-009 §9.3: aggregate before pagination so a multi-class
            # entity is never truncated into an incomplete single-class object.
            items = self._aggregate_entity_class_rows(items, with_identity=True)
        if template.name == "property-list" and class_iri:
            # Only properties that declare this class as their domain match; a
            # domain-less property never belongs to every class implicitly.
            items = [
                item
                for item in items
                if (item.get("detail_fields") or {}).get("domain") == class_iri
            ]
        # R3.0-004: drop rows referencing unauthorized members BEFORE the
        # caller's limit is applied, so pagination never leaks hidden rows.
        items = self.access_view.filter_items(items)
        paging = self._paging_state(
            limit=bounded_limit,
            returned=min(len(items), bounded_limit),
            visible_count=len(items),
            ceiling_reached=ceiling_reached,
        )
        items = items[:bounded_limit]
        if q and template.name in {"ontology-schema-summary", "entity-list"}:
            items, retrieval = self._compose_public_list_search(
                template,
                scope,
                items,
                q=q,
                class_iri=class_iri,
                limit=bounded_limit,
                search_mode=search_mode,
            )
            envelope = self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=[*warnings, *retrieval.get("warnings", [])],
                paging=paging,
            )
            envelope["recall"] = recall_summary(items, retrieval, search_mode)
            return envelope
        return self._envelope(
            template=template,
            scope=scope,
            items=items,
            warnings=warnings,
            paging=paging,
        )

    def _compose_resource_relations(
        self, template: ReadModelTemplate, scope: ScopeResolution, limit: int
    ) -> dict[str, Any]:
        resources = self.read_model(
            scope.ontology_id, "resource-list", include="asserted", limit=500,
            field_set="detail",
        )
        if resources["model_revision"] != scope.model_revision:
            raise ReadModelError("Resource scope changed during reading; refresh the graph")
        endpoints = {item["iri"] for item in resources["items"]}
        definitions: dict[str, set[str]] = {}
        for resource in resources["items"]:
            if resource.get("semantic_id"):
                definitions.setdefault(resource["semantic_id"], set()).add(resource["iri"])
        warnings = list(resources["warnings"])
        endpoint_incomplete = not resources["paging"]["complete"]
        rows = []
        fetch_incomplete = False
        if endpoints and scope.model_graph_iris:
            # Bind the governed node window before the RDF fetch ceiling. Edges
            # elsewhere in the Ontology must not consume this window's budget.
            values = ", ".join(f"<{_sparql_iri_value(iri)}>" for iri in sorted(endpoints))
            # The frozen view already resolved all project protection sets.
            # Exclude denied predicates before LIMIT just as endpoints above;
            # hidden edges must not consume the relation fetch budget.
            denied_predicates = sorted(self.access_view._unauthorized_iris)
            predicate_filter = ""
            if denied_predicates:
                denied_values = ", ".join(
                    f"<{_sparql_iri_value(iri)}>" for iri in denied_predicates
                )
                predicate_filter = f"FILTER(?relation NOT IN ({denied_values}))"
            query = self._compile_template_query(
                template, scope.model_graph_iris, _FILTERED_FETCH_LIMIT
            ).replace("{resource_iris}", values).replace(
                "{relation_access_filter}", predicate_filter
            )
            settings = getattr(self.scope_resolver, "settings", None) or Settings()
            base = settings.semantic_base_iri.rstrip("/")
            reference_predicates = [
                f"{base}/vocab/{name}" for name in (
                    "columnMappings", "joinPath", "mappingDefinition", "actionDefinition",
                    "parameterDefinition", "ruleDefinition", "parameters", "preconditions",
                    "effects",
                )
            ] + [f"{base}/property/mapping_payload"]
            query = query.replace(
                "{reference_predicates}",
                ", ".join(f"<{_sparql_iri_value(iri)}>" for iri in reference_predicates),
            )
            result = self.rdf_store.query_read_model(
                query=query, graph_iris=scope.model_graph_iris,
                timeout_seconds=self.timeout_seconds, limit=_FILTERED_FETCH_LIMIT,
            )
            rows = self._rows(result)
            fetch_incomplete = len(rows) >= _FILTERED_FETCH_LIMIT or bool(
                getattr(result, "truncated", False)
            )
        by_triple: dict[tuple[str, ...], dict[str, Any]] = {}
        expanded_rows = []
        for row in rows:
            payload = self._cell(row, "reference_payload")
            if payload is None:
                expanded_rows.append((row, ""))
                continue
            try:
                structured = json.loads(payload)
            except (ValueError, TypeError, RecursionError):
                # Neutral mapping annotations in existing models were stored
                # as Python dictionary literals. Read them without execution.
                if not str(self._cell(row, "relation")).endswith("/property/mapping_payload"):
                    continue
                try:
                    structured = ast.literal_eval(payload)
                except (ValueError, SyntaxError, TypeError, RecursionError):
                    continue
            if self.access_view.any_unauthorized([structured]):
                continue
            for target, field_path in _explicit_resource_references(structured, definitions):
                expanded_rows.append(({**row, "target": target}, field_path))
        for row, field_path in expanded_rows:
            item = self._decorate_row(row, scope, template)
            if item.get("source") not in endpoints or item.get("target") not in endpoints:
                continue
            if self.access_view.any_unauthorized([item.get("label")]):
                item["label"] = None
            triple = (item["source"], item["relation"], item["target"])
            identity = (*triple, field_path) if field_path else triple
            item["edge_kind"] = "structured_reference" if field_path else "rdf_relation"
            if field_path:
                item["field_path"] = field_path
                item["label"] = field_path
            if not self.access_view.filter_items([item]):
                continue
            # Structured references also retain their exact field position.
            item["id"] = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            previous = by_triple.get(identity)
            if previous is None or (
                item.get("label") or "",
            ) < (previous.get("label") or "",):
                by_triple[identity] = item
        items = [by_triple[key] for key in sorted(by_triple)]
        paging = self._paging_state(
            limit=limit, returned=min(len(items), limit), visible_count=len(items),
            ceiling_reached=endpoint_incomplete or fetch_incomplete,
        )
        if endpoint_incomplete:
            warnings.append({
                "code": "resource_relations_endpoint_window_incomplete",
                "message": "Relations cover a partial loaded resource window.",
            })
        if fetch_incomplete:
            warnings.append({
                "code": "read_model_rows_truncated",
                "message": "Resource relation fetch is incomplete; this page may omit relations.",
            })
        if paging["has_more"]:
            warnings.append({
                "code": "resource_relations_window_incomplete",
                "message": "The authorized relation window has more items than this page.",
            })
        return self._envelope(
            template=template, scope=scope, items=items[:limit], warnings=warnings, paging=paging,
        )

    def _envelope(
        self,
        *,
        template: ReadModelTemplate,
        scope: ScopeResolution,
        items: list[dict[str, Any]],
        warnings: list[dict[str, str]],
        paging: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.scope_resolver.resolve(scope.ontology_id, include=scope.include)
        if current.model_revision != scope.model_revision:
            raise ReadModelError("Model revision changed during reading; refresh the model")
        envelope = {
            "ontology_id": scope.ontology_id,
            "model_revision": scope.model_revision,
            "projection_version": template.projection_version,
            "model_name": template.name,
            "include": scope.include,
            "derived_state": scope.derived_state,
            "warnings": warnings,
            "items": items,
        }
        if paging is not None:
            envelope["paging"] = paging
        return envelope

    @staticmethod
    def _paging_state(
        *, limit: int, returned: int, visible_count: int, ceiling_reached: bool
    ) -> dict[str, Any]:
        """Window state of one page relative to the authorized visible set.

        R3.0-009 §6.2: ``has_more``/``truncated``/``complete`` only describe
        what the caller is authorized to see, so a hidden member can never be
        inferred from them. ``visible_count`` counts authorized items seen
        before the page was cut; it is a lower bound when ``truncated`` is
        true because the fetch ceiling was reached.
        """
        has_more = visible_count > limit
        return {
            "limit": limit,
            "returned": returned,
            "visible_count": visible_count,
            "has_more": has_more,
            "truncated": bool(ceiling_reached),
            "complete": not (has_more or ceiling_reached),
        }

    def _fetch_limit(self, bounded_limit: int) -> int:
        """Elevate the fetch limit while access filtering so filtering happens
        before the caller-visible pagination."""
        if self.access_view.requires_filtering:
            return max(bounded_limit, _FILTERED_FETCH_LIMIT)
        # One extra row is the cheapest reliable ``has_more`` signal.
        return bounded_limit + 1

    def _expanded_fetch_limit(self, bounded_limit: int) -> int:
        """Fetch head room for models that post-process rows before pagination.

        ``entity-list`` returns one row per (entity, class) pair and is
        aggregated per entity, and ``property-list`` post-filters declared
        domains; both need extra rows so one caller page is not cut short.
        The cap stays bounded by the same filtered-fetch ceiling.
        """
        elevated = self._fetch_limit(bounded_limit)
        expanded = max(
            elevated * _ROW_POST_PROCESS_FETCH_MULTIPLIER,
            bounded_limit + _ROW_POST_PROCESS_FETCH_FLOOR,
        )
        return min(expanded, _FILTERED_FETCH_LIMIT)

    @staticmethod
    def _aggregate_entity_class_rows(
        items: list[dict[str, Any]], *, with_identity: bool
    ) -> list[dict[str, Any]]:
        """Collapse one row per (entity, visible formal class) pair into one
        item per entity (R3.0-009 §6.2/§9.3).

        ``class_iris`` carries the full visible formal class set (deduplicated
        and sorted by expanded IRI, so order is stable); the legacy scalar
        ``class_iri``/``class_label`` project the lexicographically first
        visible class, or null when the entity has none — the scalar is never a
        multi-class truth. Entities keep their first-appearance order so the
        template ORDER BY stays authoritative. When ``with_identity`` is set, a
        visible class without its own ``/vocab/id`` is reported through
        ``incomplete_class_identity_iris`` instead of dropping the node; hidden
        classes never appear because access filtering runs on the aggregate.
        """
        grouped: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in items:
            iri = str(item.get("iri") or "")
            entry = grouped.get(iri)
            if entry is None:
                entry = {"item": {**item}, "classes": {}}
                grouped[iri] = entry
                order.append(iri)
            class_iri = item.get("class_iri")
            if not (isinstance(class_iri, str) and class_iri):
                continue
            record = entry["classes"].setdefault(
                class_iri,
                {
                    "class_iri": class_iri,
                    "class_semantic_id": item.get("class_semantic_id"),
                    "class_label": item.get("class_label"),
                },
            )
            if record.get("class_semantic_id") is None:
                record["class_semantic_id"] = item.get("class_semantic_id")
            if record.get("class_label") is None:
                record["class_label"] = item.get("class_label")
        aggregated: list[dict[str, Any]] = []
        for iri in order:
            entry = grouped[iri]
            item = entry["item"]
            classes = [entry["classes"][key] for key in sorted(entry["classes"])]
            item["class_iris"] = [record["class_iri"] for record in classes]
            item["class_iri"] = classes[0]["class_iri"] if classes else None
            item["class_label"] = classes[0]["class_label"] if classes else None
            if with_identity:
                item["class_semantic_id"] = (
                    classes[0]["class_semantic_id"] if classes else None
                )
                incomplete = [
                    record["class_iri"]
                    for record in classes
                    if not (
                        isinstance(record.get("class_semantic_id"), str)
                        and record["class_semantic_id"]
                    )
                ]
                if incomplete:
                    item["incomplete_class_identity_iris"] = incomplete
            aggregated.append(item)
        return aggregated

    @staticmethod
    def _compile_template_query(
        template: ReadModelTemplate,
        graph_iris: list[str],
        limit: int,
        *,
        entity_iri: str | None = None,
    ) -> str:
        values = " ".join(f"<{iri}>" for iri in graph_iris)
        query = (
            template.body.replace("{graph_iris}", values)
            .replace("{limit}", str(int(limit)))
        )
        if "{entity_iri}" in query:
            if not entity_iri:
                raise ReadModelError(f"{template.name} requires an entity IRI")
            query = query.replace("{entity_iri}", _sparql_iri_value(entity_iri))
        elif entity_iri and template.name in {
            "entity-detail", "class-detail", "property-list", "relation-type-list",
        }:
            # Exact resource lookup binds identity before LIMIT/authorization;
            # it must not search only the first page of a broad listing.
            target = _sparql_iri_value(entity_iri)
            query = query.replace(
                "WHERE {",
                f"WHERE {{ VALUES ?{template.primary_iri_variable} {{ <{target}> }}",
                1,
            )
        return query

    def _graph_iris_for_scope(
        self, scope: ScopeResolution, template: ReadModelTemplate
    ) -> list[str]:
        if template.name == "statement-list":
            return list(scope.model_graph_iris)
        iris = list(scope.model_graph_iris)
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
        iri = self._row_iri(row, template)
        label = self._cell(row, "label")
        model_graph_iri = self._cell(row, "graph")
        if not model_graph_iri:
            model_graph_iri = scope.model_graph_iris[0] if scope.model_graph_iris else ""
        display_fields = self._graph_display_fields(row)
        if template.name == "entity-list":
            # Keep the existing id/iri aliases for compatibility, while making
            # the canonical identity projection explicit for Protocol callers.
            display_fields["entity_iri"] = iri
        item = {
            "id": iri,
            "iri": iri,
            "label": label,
            "ontology_id": scope.ontology_id,
            "assertion_kind": self._assertion_kind_for(model_graph_iri, scope, template),
            "audit_status": "system_accepted",
            "staleness": {
                "is_stale": self._is_stale(model_graph_iri, scope),
                "reason": self._staleness_reason(model_graph_iri, scope),
            },
            **display_fields,
        }
        # R3.0-003: incremental passthrough of template-declared non-whitelist
        # projection variables into a stable detail_fields subobject. The
        # default (no declared variables) keeps responses byte-identical.
        detail_fields = self._detail_fields(row, template)
        if detail_fields:
            item["detail_fields"] = detail_fields
        return item

    @staticmethod
    def _detail_fields(
        row: dict[str, Any], template: ReadModelTemplate
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for variable in template.detail_variables:
            if variable in _READ_MODEL_WHITELIST_VARIABLES:
                continue
            value = SemanticReadModelService._cell(row, variable)
            if value is not None:
                if variable in {
                    "semantic_definition", "mapping_definition", "action_definition",
                    "parameter_definition",
                } or template.name in {"operation-list", "operation-detail"} and variable in {
                    "parameters", "preconditions", "effects", "possible_failures", "idempotency",
                    "tool_bindings", "credential_requirements",
                }:
                    try:
                        value = json.loads(value)
                    except (ValueError, TypeError):
                        # Direct RDF writes may contain an uninterpreted literal;
                        # preserve it rather than inventing a business meaning.
                        pass
                fields[variable] = value
        return fields

    def _graph_display_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for key in (
            "semantic_id",
            "parent",
            "class",
            "class_semantic_id",
            "class_label",
            "source",
            "target",
            "relation",
            "range",
            "type",
        ):
            value = self._cell(row, key)
            if value is not None:
                fields[_READ_MODEL_FIELD_ALIASES.get(key, key)] = value
        for key in ("subject", "predicate", "object"):
            value = self._cell(row, key)
            if value is not None:
                fields[key] = value
        if "object" in fields:
            object_is_iri = self._cell_is_uri(row, "object")
            fields["object_kind"] = "iri" if object_is_iri else "literal"
            if not object_is_iri:
                object_datatype = self._cell_datatype(row, "object")
                object_language = self._cell_lang(row, "object")
                if object_datatype is not None:
                    fields["object_datatype"] = object_datatype
                if object_language is not None:
                    fields["object_language"] = object_language
        return fields

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

    @staticmethod
    def _cell_is_uri(row: dict[str, Any], key: str) -> bool:
        if key not in row:
            return False
        value = row[key]
        if isinstance(value, dict):
            return value.get("type") == "uri"
        return False

    @staticmethod
    def _cell_datatype(row: dict[str, Any], key: str) -> str | None:
        """Extract the XSD datatype IRI for a typed literal cell, if any.

        Standard SPARQL JSON results encode typed literals as
        ``{"value": ..., "type": "literal", "datatype": "<iri>"}`` (or
        ``type: "typed-literal"`` in older serializers). Returns ``None``
        for plain literals, IRIs, or missing cells.
        """
        if key not in row:
            return None
        value = row[key]
        if isinstance(value, dict):
            if value.get("type") not in ("literal", "typed-literal"):
                return None
            datatype = value.get("datatype")
            return str(datatype) if datatype else None
        return None

    @staticmethod
    def _cell_lang(row: dict[str, Any], key: str) -> str | None:
        """Extract the language tag (``xml:lang``) for a lang-tagged literal cell.

        SPARQL JSON results encode lang-tagged literals as
        ``{"value": ..., "type": "literal", "xml:lang": "en"}``. Returns
        ``None`` for plain/typed literals, IRIs, or missing cells.
        """
        if key not in row:
            return None
        value = row[key]
        if isinstance(value, dict):
            if value.get("type") not in ("literal", "typed-literal"):
                return None
            lang = value.get("xml:lang")
            return str(lang) if lang else None
        return None

    def _row_iri(self, row: dict[str, Any], template: ReadModelTemplate) -> str:
        """Pick the row's primary IRI using the template's declared variable
        first, then a small fallback chain so legacy / unknown templates that
        project one of the common subject variables still resolve."""
        primary = template.primary_iri_variable
        if primary:
            value = self._cell(row, primary)
            if value:
                return value
            # Some templates' SELECT variables rename across versions; fall
            # through to the legacy chain rather than returning empty.
        for fallback in ("class", "entity", "subject", "iri"):
            value = self._cell(row, fallback)
            if value:
                return value
        return ""


    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # ------------------------------------------------------------------




    # ------------------------------------------------------------------
    # publication-readiness composer (Stage 3 §4.1)
    # ------------------------------------------------------------------

    def _compose_publication_readiness(self, scope, field_set):
        freshness = self._projection_freshness(scope.ontology_id)
        gates = self._evaluate_publication_gates(staleness_row={}, open_edits=0,
                                                  projection_freshness=freshness)
        return {"ontology_id": scope.ontology_id, "ready": True, "gates": gates,
                "blockers": [], "warnings": [g["label"] for g in gates if g["status"] == "warning"]}


    def _projection_freshness(self, ontology_id: str) -> dict[str, dict[str, Any]]:
        """Returns {manifest_projection_kind: {fresh, last_run_at}}."""
        if self.session is None:
            return {}
        from sqlalchemy import select

        from app.repositories.models import SemanticProjectionManifestModel

        rows = list(
            self.session.scalars(
                select(SemanticProjectionManifestModel).where(
                    SemanticProjectionManifestModel.ontology_id == ontology_id
                )
            )
        )
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            out[r.projection_kind] = {
                "fresh": r.updated_at is not None,
                "last_run_at": r.updated_at.isoformat() if r.updated_at else None,
            }
        return out


    def _evaluate_publication_gates(
        self,
        *,
        staleness_row: dict[str, Any],
        open_edits: int,
        projection_freshness: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Map staleness, open edits, and projection signals to the
        ``GateStatus`` shape."""
        gates: list[dict[str, Any]] = []
        # open_edits is intentionally a warning (not a blocker): pending edits
        # are recoverable — publication can proceed, but the user is alerted.
        gates.append({
            "gate": "open_edits",
            "status": "passed" if open_edits == 0 else "warning",
            "details": {"count": open_edits},
            "label": f"{open_edits} pending semantic edits",
        })
        fresh_all = bool(projection_freshness) and all(
            p["fresh"] for p in projection_freshness.values()
        )
        gates.append({
            "gate": "projection_freshness",
            "status": "passed" if fresh_all else "warning",
            "details": projection_freshness,
            "label": "projection manifest freshness",
        })
        return gates

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------



    # ------------------------------------------------------------------
    # ------------------------------------------------------------------




    # ------------------------------------------------------------------
    # fact-audit-queue composer (Stage 2 §6.3)
    # ------------------------------------------------------------------

    _FACT_KINDS = ("asserted",)

    def _compose_fact_audit_queue(
        self,
        scope: ScopeResolution,
        kind: str | None,
        field_set: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Compose the FactAuditPage queue by ``?kind=``.

        kind selects the source graph(s):

        - ``asserted`` → the selected Ontology model.

        Each row is decorated into the unified FactRow shape (spec §6.3):
        id, assertion_kind, subject_iri, subject_label, predicate_iri,
        predicate_label, object_value, object_label, graph_iri,
        audit_status, derived_from (when applicable), stale, stale_reason.
        """
        resolved_kind = (kind or "asserted").strip()
        if resolved_kind not in self._FACT_KINDS:
            raise ReadModelError(
                f"Unsupported fact-audit-queue kind: {resolved_kind}. "
                f"Must be one of: {', '.join(self._FACT_KINDS)}"
            )

        warnings: list[dict[str, str]] = list(scope.warnings)
        if resolved_kind == "asserted":
            data_iris = list(scope.model_graph_iris)
            if not data_iris:
                return [], warnings + [
                    {
                        "code": "fact_audit_no_asserted_data",
                        "message": "Ontology model is unavailable.",
                    }
                ]
            rows = self._fetch_fact_rows(
                data_iris, template_name="fact-audit-queue"
            )
            items = [
                self._decorate_fact_row(
                    row,
                    assertion_kind=resolved_kind,
                    scope=scope,
                )
                for row in rows
            ]
            return items, warnings

    def _compose_entity_literal_facts(
        self,
        template: ReadModelTemplate,
        scope: ScopeResolution,
        entity_iri: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not entity_iri:
            raise ReadModelError("entity-literal-facts requires the entity query parameter")
        graph_iris = self._graph_iris_for_scope(scope, template)
        rows = self._fetch_fact_rows(
            graph_iris,
            "entity-literal-facts",
            entity_iri=entity_iri,
            limit=limit,
        )
        items = [
            self._decorate_fact_row(
                row,
                assertion_kind=self._assertion_kind_for(
                    self._cell(row, "graph") or "",
                    scope,
                    template,
                ),
                scope=scope,
            )
            for row in rows
            if not self._cell_is_uri(row, "object")
        ]
        return items

    def _fetch_fact_rows(
        self,
        graph_iris: list[str],
        template_name: str,
        *,
        entity_iri: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Run the fact-audit-queue template against the
        given source graphs and return raw SPARQL rows."""
        if not graph_iris:
            return []
        template = get_template(template_name)
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        fetch_limit = self._fetch_limit(bounded_limit)
        query = self._compile_template_query(
            template,
            graph_iris,
            fetch_limit,
            entity_iri=entity_iri,
        )
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=graph_iris,
            timeout_seconds=self.timeout_seconds,
            limit=fetch_limit,
        )
        rows = self.access_view.filter_statement_rows(
            list(self._rows(result)),
            subject_key="subject",
            predicate_key="predicate",
            object_keys=("object",),
        )
        return rows[: bounded_limit if self.access_view.requires_filtering else None]

    def _decorate_fact_row(
        self,
        row: dict[str, Any],
        *,
        assertion_kind: str,
        scope: ScopeResolution,
        derived_run_id: str | None = None,
        stale: bool | None = None,
        stale_reason: str | None = None,
    ) -> dict[str, Any]:
        """Decorate a raw SPARQL row into the unified FactRow shape."""
        subject_iri = self._cell(row, "subject") or ""
        subject_label = self._cell(row, "subject_label")
        predicate_iri = self._cell(row, "predicate") or ""
        predicate_label = self._cell(row, "predicate_label")
        object_value: Any = self._cell(row, "object")
        object_is_iri = self._cell_is_uri(row, "object")
        object_label = self._cell(row, "object_label")
        model_graph_iri = self._cell(row, "graph") or (
            scope.model_graph_iris[0] if scope.model_graph_iris else ""
        )
        # Audit status defaults to "pending" — the FactAuditPage surfaces
        # the audit_status that may be set on the row by an RDF-star
        # reification in a later iteration; absent that, everything is
        # pending review.
        audit_status = self._cell(row, "audit_status") or "pending"
        # Stable id: 4-tuple sha256 from ``compute_fact_id``. Preserve
        # datatype/lang so typed and language-tagged literals retain a stable
        # identity across read paths.
        object_datatype = (
            self._cell_datatype(row, "object") if not object_is_iri else None
        )
        object_lang = self._cell_lang(row, "object") if not object_is_iri else None
        object_term = canonical_object_term(
            str(object_value) if object_value is not None else "",
            is_iri=object_is_iri,
            datatype=object_datatype,
            lang=object_lang,
        )
        fact_id = compute_fact_id(
            subject_iri, predicate_iri, object_term, model_graph_iri
        )
        # Staleness for derived graphs.
        if stale is None:
            stale_bool = self._is_stale(model_graph_iri, scope)
        else:
            stale_bool = bool(stale)
        if stale_reason is None:
            stale_reason_val = self._staleness_reason(model_graph_iri, scope)
        else:
            stale_reason_val = stale_reason
        item: dict[str, Any] = {
            "id": fact_id,
            "fact_id": fact_id,
            "assertion_kind": assertion_kind,
            "subject_iri": subject_iri,
            "subject_label": subject_label,
            "predicate_iri": predicate_iri,
            "predicate_label": predicate_label,
            "object_value": object_value,
            "object_is_iri": object_is_iri,
            "object_label": object_label,
            "ontology_id": scope.ontology_id,
            "audit_status": audit_status,
            "stale": stale_bool,
            "stale_reason": stale_reason_val,
        }
        if derived_run_id is not None:
            item["derived_from"] = {"run_id": derived_run_id}
        return item

    # ------------------------------------------------------------------
    # entity-search composer (Stage 4 §4.1)
    # ------------------------------------------------------------------

    def _compose_entity_search(
        self,
        template: ReadModelTemplate,
        scope: ScopeResolution,
        *,
        q: str | None,
        class_iri: str | None,
        limit: int,
        field_set: str,
        search_mode: str = "hybrid",
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Run the entity-search SPARQL against the active scope's data graphs,
        decorating each row with the standard decorator plus the
        ``comment`` / ``class_iri`` / ``class_label`` / ``ontology_id``
        extensions declared in spec §4.1."""
        graph_iris = list(scope.model_graph_iris) or []
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        # R3.0-009 §9.3: rows are one per (entity, class) pair and are
        # aggregated per entity, so fetch extra head room before pagination.
        fetch_limit = self._expanded_fetch_limit(bounded_limit)
        body = template.body
        body = body.replace("{graph_iris}", " ".join(f"<{i}>" for i in graph_iris))
        body = body.replace("{limit}", str(fetch_limit))
        # Bind the search substring ?q as a literal. Defaulting to the empty
        # string makes the FILTER a no-op so the same template can serve an
        # unfiltered listing call. A comment marker is appended so test fakes
        # can extract the value without parsing SPARQL.
        bound_q = q if q is not None else ""
        body = body.replace("?q", f'"{bound_q}"')
        body = body + f"\n# q_filter: \"{bound_q}\""
        # Bind the class filter in place. A VALUES preamble before PREFIX
        # declarations makes Oxigraph parse the query as malformed, so keep
        # the query prologue intact and rewrite only the filter expressions.
        class_filter_expr = "FILTER(!BOUND(?class_iri) || ?class = ?class_iri)"
        if class_iri is not None:
            body = body.replace(class_filter_expr, f"FILTER(?class = <{class_iri}>)")
            # Only entities that are formal members of the requested class
            # match; a zero-class entity never satisfies an explicit filter.
            body = body.replace(
                "FILTER({class_guard})",
                "FILTER(BOUND(?class))",
            )
            body = body + f"\n# class_iri_filter: <{class_iri}>"
        else:
            body = body.replace(
                "FILTER({class_guard})",
                "FILTER(!BOUND(?class_iri) || BOUND(?class))",
            )
        result = self.rdf_store.query_read_model(
            query=body,
            graph_iris=graph_iris,
            timeout_seconds=self.timeout_seconds,
            limit=fetch_limit,
        )
        rows = self._rows(result)
        items: list[dict[str, Any]] = []
        for row in rows:
            decorated = self._decorate_row(row, scope, template)
            # Stage 4 §4.1 additional fields not provided by the base decorator.
            decorated["comment"] = self._cell(row, "comment")
            decorated["class_iri"] = self._cell(row, "class")
            decorated["class_label"] = self._cell(row, "class_label")
            decorated["ontology_id"] = scope.ontology_id
            items.append(decorated)
        items = self._aggregate_entity_class_rows(items, with_identity=False)
        items = self.access_view.filter_items(items)
        retrieval: dict[str, Any] = {
            "candidates": [], "indexes": [], "warnings": [], "completeness": "complete"
        }
        if q:
            semantic_items: list[dict[str, Any]] = []
            if self.retrieval_service is not None:
                retrieval = self.retrieval_service.recall_ontology(
                    scope=scope,
                    query=q,
                    resource_kinds={"instance"},
                    search_mode=search_mode,
                    limit=bounded_limit,
                )
                semantic_items = retrieval["candidates"]
            semantic_items = [
                item for item in semantic_items if self.access_view.filter_candidate(item)
            ]
            promote_exact_label_candidates(semantic_items, q)
            if class_iri:
                semantic_items = [
                    item
                    for item in semantic_items
                    if class_iri in item.get("data", {}).get("rdf_types", [])
                ]
            ontology_id = scope.ontology_id
            lexical_items = [
                self._entity_lexical_candidate(item, q, ontology_id) for item in items
            ]
            mapping_candidates = [
                candidate
                for candidate in governed_mapping_lexical_candidates(
                    self.session,
                    ontology_ids=[ontology_id],
                    query=q,
                    resource_kinds={"instance"},
                )
                if self.access_view.filter_candidate(candidate)
            ]
            semantic_rows = [
                self._entity_semantic_row(candidate, scope)
                for candidate in [*semantic_items, *mapping_candidates]
            ]
            items = fuse_context_candidates(lexical_items, semantic_rows)
            items = self.access_view.filter_items(items)
            items.sort(key=_entity_search_sort_key)
            items = items[:bounded_limit]
        return items, retrieval

    def _compose_public_list_search(
        self,
        template: ReadModelTemplate,
        scope: ScopeResolution,
        items: list[dict[str, Any]],
        *,
        q: str,
        class_iri: str | None,
        limit: int,
        search_mode: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Add hybrid recall to legacy public list models without changing rows.

        ``entity-list`` and ``ontology-schema-summary`` are established public
        contracts.  Their SPARQL templates still provide canonical row shape;
        this adapter merely filters lexical rows and merges scope-fenced recall
        candidates into that same shape when callers supply ``q``.
        """
        resource_kind = "instance" if template.name == "entity-list" else "concept"
        ontology_id = scope.ontology_id
        lexical_items = [
            candidate
            for item in items
            if (
                candidate := self._public_list_lexical_candidate(
                    item,
                    q,
                    ontology_id,
                    resource_kind,
                    class_iri,
                )
            )
            is not None
        ]
        retrieval: dict[str, Any] = {
            "candidates": [], "indexes": [], "warnings": [], "completeness": "complete"
        }
        semantic_items: list[dict[str, Any]] = []
        if self.retrieval_service is not None:
            retrieval = self.retrieval_service.recall_ontology(
                scope=scope,
                query=q,
                resource_kinds={resource_kind},
                search_mode=search_mode,
                limit=limit,
            )
            semantic_items = retrieval["candidates"]
        semantic_items = [
            item for item in semantic_items if self.access_view.filter_candidate(item)
        ]
        promote_exact_label_candidates(semantic_items, q)
        if class_iri and resource_kind == "instance":
            semantic_items = [
                item
                for item in semantic_items
                if class_iri in item.get("data", {}).get("rdf_types", [])
            ]
        canonical_by_iri = {
            str(item.get("iri")): item
            for item in items
            if isinstance(item, dict)
            and all(
                isinstance(item.get(field), str) and item.get(field)
                for field in ("semantic_id", "entity_iri")
            )
        }
        semantic_rows = []
        for candidate in [
            *semantic_items,
            *governed_mapping_lexical_candidates(
                self.session,
                ontology_ids=[ontology_id],
                query=q,
                resource_kinds={resource_kind},
            ),
        ]:
            if not self.access_view.filter_candidate(candidate):
                continue
            row = self._public_list_semantic_row(
                candidate,
                scope,
                template,
                canonical=canonical_by_iri.get(str(candidate.get("iri") or candidate.get("id"))),
            )
            if row is not None:
                semantic_rows.append(row)
        fused = fuse_context_candidates(lexical_items, semantic_rows)
        fused = self.access_view.filter_items(fused)
        fused.sort(key=_entity_search_sort_key)
        return fused[:limit], retrieval

    @staticmethod
    def _public_list_lexical_candidate(
        item: dict[str, Any],
        query: str,
        ontology_id: str,
        resource_kind: str,
        class_iri: str | None,
    ) -> dict[str, Any] | None:
        if class_iri and resource_kind == "instance":
            # R3.0-009 §9.3: the class filter matches the full visible
            # class_iris set, never only the legacy scalar projection.
            class_iris = item.get("class_iris")
            members = (
                class_iris
                if isinstance(class_iris, list)
                else ([item.get("class_iri")] if item.get("class_iri") else [])
            )
            if class_iri not in members:
                return None
        normalized_query = normalize_retrieval_text(query)
        label = normalize_retrieval_text(str(item.get("label") or ""))
        iri = normalize_retrieval_text(str(item.get("iri") or ""))
        if label == normalized_query:
            score, reason, field = 1000, "exact_label", "label"
        elif iri == normalized_query:
            score, reason, field = 600, "identifier", "identifier"
        elif normalized_query and normalized_query in label:
            score, reason, field = 750, "label_contains", "label"
        else:
            return None
        return {
            **item,
            "kind": resource_kind,
            "ontology_id": ontology_id,
            "match": {
                "score": score,
                "reasons": [reason],
                "matched_fields": [field],
                "matched_terms": [normalized_query],
            },
        }

    @staticmethod
    def _public_list_semantic_row(
        candidate: dict[str, Any],
        scope: ScopeResolution,
        template: ReadModelTemplate,
        *,
        canonical: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        item = {
            **candidate,
            "ontology_id": scope.ontology_id,
            "audit_status": "system_accepted",
            "staleness": {"is_stale": False, "reason": None},
        }
        if template.name == "entity-list":
            projection = canonical or candidate
            if not all(
                isinstance(projection.get(field), str) and projection.get(field)
                for field in ("semantic_id", "entity_iri")
            ):
                # Retrieval rows are ranking hints, not an identity authority.
                # Never return a Protocol-facing entity without the explicit
                # backend projection that binds its stable identity. Class
                # membership is optional metadata (R3.0-009 §9.3), not identity.
                return None
            class_iris = projection.get("class_iris")
            if not isinstance(class_iris, list):
                scalar = projection.get("class_iri")
                class_iris = [scalar] if isinstance(scalar, str) and scalar else []
            visible_classes = sorted(
                {value for value in class_iris if isinstance(value, str) and value}
            )
            item.update(
                {
                    "semantic_id": projection["semantic_id"],
                    "entity_iri": projection["entity_iri"],
                    "class_iris": visible_classes,
                    "class_iri": visible_classes[0] if visible_classes else None,
                    "class_semantic_id": projection.get("class_semantic_id"),
                    "class_label": projection.get("class_label"),
                }
            )
        return item


    @staticmethod
    def _entity_lexical_candidate(
        item: dict[str, Any], query: str, ontology_id: str
    ) -> dict[str, Any]:
        label = item.get("label") or item.get("iri") or ""
        normalized_query = normalize_retrieval_text(query)
        normalized_label = normalize_retrieval_text(str(label))
        normalized_iri = normalize_retrieval_text(str(item.get("iri") or ""))
        if normalized_label == normalized_query:
            score, reason, field = 1000, "exact_label", "label"
        elif normalized_iri == normalized_query:
            score, reason, field = 600, "identifier", "identifier"
        elif normalized_query and normalized_query in normalized_label:
            score, reason, field = 750, "label_contains", "label"
        else:
            score, reason, field = 450, "description_contains", "description"
        return {
            **item,
            "kind": "instance",
            "ontology_id": ontology_id,
            "match": {
                "score": score,
                "reasons": [reason],
                "matched_fields": [field],
                "matched_terms": [normalized_query],
            },
        }

    @staticmethod
    def _entity_semantic_row(candidate: dict[str, Any], scope: ScopeResolution) -> dict[str, Any]:
        rdf_types = list(candidate.get("data", {}).get("rdf_types", []))
        return {
            **candidate,
            "audit_status": "system_accepted",
            "staleness": {"is_stale": False, "reason": None},
            "comment": candidate.get("description"),
            "class_iri": rdf_types[0] if rdf_types else None,
            "class_label": None,
            "ontology_id": scope.ontology_id,
        }

    # ------------------------------------------------------------------


    def _assertion_kind_for(self, model_graph_iri, scope, template) -> str:
        return "asserted" if template.assertion_kind == "any" else template.assertion_kind

    def _is_stale(self, model_graph_iri, scope) -> bool:
        return False

    def _staleness_reason(self, model_graph_iri, scope) -> None:
        return None


def _explicit_resource_references(
    value: Any, definitions: dict[str, set[str]], path: str = ""
) -> list[tuple[str, str]]:
    """Read explicit reference slots only; never interpret descriptions or names."""
    references = []
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            field_path = f"{path}.{key}" if path else key
            if key == "definition_ref" and isinstance(child, str):
                targets = definitions.get(child, set())
                if len(targets) == 1:
                    references.append((next(iter(targets)), field_path))
            elif key.endswith("_iri") and isinstance(child, str):
                references.append((child, field_path))
            elif key.endswith("_iris") and isinstance(child, list):
                references.extend(
                    (target, f"{field_path}[{index}]")
                    for index, target in enumerate(child) if isinstance(target, str)
                )
            elif isinstance(child, (dict, list)):
                references.extend(_explicit_resource_references(child, definitions, field_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            references.extend(_explicit_resource_references(child, definitions, f"{path}[{index}]"))
    return references


def _sparql_iri_value(value: str) -> str:
    """Validate an IRI string before embedding it between SPARQL angle brackets."""
    stripped = value.strip()
    if not stripped or any(ch in stripped for ch in "<> \t\r\n"):
        raise ReadModelError("Invalid entity IRI")
    return stripped


def _entity_search_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    """Keep entity results deterministic while preferring evidence-backed matches."""
    match = item.get("match") or {}
    is_exact = match.get("candidate_level") == "exact"
    score = int(match.get("score", 0) or 0)
    return (
        0 if is_exact else 1,
        -score,
        normalize_retrieval_text(str(item.get("label") or "")),
        str(item.get("iri") or ""),
    )
