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

from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.repositories.rdf_store import RdfStoreRepository
from app.services.fact_id import canonical_object_term, compute_fact_id
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


_READ_MODEL_FIELD_ALIASES = {
    "class": "class_iri",
    "range": "range_iri",
    "type": "type_iri",
}


class SemanticReadModelService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        timeout_seconds: float = 5.0,
        default_limit: int = 500,
        visibility_policy: _VisibilityPolicy | None = None,
        shape_endpoint: _ShapeEndpointProtocol | None = None,
        session: Any = None,
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
        # Stage 3 composers (publication-readiness, graph-set-history-list,
        # graph-set-delta) need direct Postgres access. The API layer passes
        # the request-scoped session here; older composers (graph-set-staleness,
        # entity-shape, fact-audit-queue) keep using ``scope_resolver`` only.
        self.session = session

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
        kind: str | None = None,
        target: str | None = None,
        q: str | None = None,
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
        if template.name == "publication-readiness":
            items = [self._compose_publication_readiness(scope, field_set)]
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
        if template.name == "graph-set-history-list":
            item = self._compose_graph_set_history_list(scope)
            return self._envelope(
                template=template,
                scope=scope,
                items=[item],
                warnings=list(scope.warnings),
            )
        if template.name == "graph-set-delta":
            item = self._compose_graph_set_delta(
                scope, target, limit or template.default_limit
            )
            return self._envelope(
                template=template,
                scope=scope,
                items=[item],
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
        if template.name == "owl-consistency-summary":
            items = [self._compose_owl_consistency_summary(scope, field_set)]
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
        if template.name == "entity-search":
            items = self._compose_entity_search(
                template,
                scope,
                q=q,
                class_iri=class_iri,
                limit=limit or template.default_limit,
                field_set=field_set,
            )
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
        if template.name == "agent-test-context":
            items = self._compose_agent_test_context(
                template,
                scope,
                q=q,
                limit=limit or template.default_limit,
                field_set=field_set,
            )
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=list(scope.warnings),
            )
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        if not graph_iris and "{graph_iris}" in template.body:
            return self._envelope(
                template=template,
                scope=scope,
                items=[],
                warnings=list(scope.warnings)
                + [
                    {
                        "code": "read_model_no_source_graphs",
                        "message": (
                            f"No source graphs are available for read model "
                            f"{template.name}."
                        ),
                    }
                ],
            )
        query = self._compile_template_query(
            template,
            graph_iris,
            bounded_limit,
            entity_iri=entity_iri,
        )
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
        return query

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
        iri = self._row_iri(row, template)
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
            **self._graph_display_fields(row),
        }

    def _graph_display_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for key in (
            "parent",
            "class",
            "class_label",
            "source",
            "target",
            "relation",
            "range",
            "type",
            "evidence_status",
        ):
            value = self._cell(row, key)
            if value is not None:
                fields[_READ_MODEL_FIELD_ALIASES.get(key, key)] = value
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
        # Stage 4 templates (entity-search, agent-test-context) declare
        # assertion_kind="any" because the SPARQL may match rows from the
        # asserted, reasoning, or rule graph depending on the include scope.
        # When the row actually came from an asserted source graph, "any"
        # resolves to "asserted" so the AssertionKind chip on the UI carries
        # the meaningful value (matches spec §4.1 decorator contract).
        if template.assertion_kind == "any":
            return "asserted"
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
        """Count asserted facts in scope that have zero evidence bindings.

        Phase 3 refactor: this used to issue a SPARQL COUNT over
        ``op:evidenceStatus "missing_evidence"`` markers. It now enumerates
        all asserted fact_ids in scope via a SELECT DISTINCT and subtracts
        the subset that have at least one row in ``fact_evidence_bindings``.
        """
        if self.session is None:
            return 0
        fact_ids = self._list_asserted_fact_ids(scope)
        if not fact_ids:
            return 0
        repo = FactEvidenceBindingRepository(self.session)
        with_bindings = repo.count_facts_with_bindings(fact_ids)
        return len(fact_ids) - len(with_bindings)

    # ------------------------------------------------------------------
    # Phase 3 — Postgres-backed evidence decoration
    # ------------------------------------------------------------------

    def _fetch_evidence_bindings_from_pg(
        self, fact_ids: list[str], session: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Batch-fetch evidence bindings from Postgres, bucketed by fact_id.

        Each binding is rendered as a dict suitable for direct inclusion in
        ``FactRow.evidence_bindings``.
        """
        if not fact_ids:
            return {}
        repo = FactEvidenceBindingRepository(session)
        raw = repo.list_by_fact_ids(fact_ids)
        return {
            fid: [self._format_evidence_binding(b) for b in bindings]
            for fid, bindings in raw.items()
        }

    @staticmethod
    def _format_evidence_binding(b: Any) -> dict[str, Any]:
        """Render a ``FactEvidenceBindingModel`` row as a FactRow dict."""
        text = b.text or ""
        return {
            "id": b.id,
            "fact_id": b.fact_id,
            "chunk_id": b.chunk_id,
            "evidence_artifact_id": b.evidence_artifact_id,
            "document_filename": b.document_filename,
            "sequence": b.sequence,
            "char_start": b.char_start,
            "char_end": b.char_end,
            "text_preview": (text[:200] + "..." if len(text) > 200 else text),
            "text": text,
            "actor": b.actor,
            "reason": b.reason,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }

    def _list_asserted_fact_ids(
        self, scope: ScopeResolution, limit: int = 5000
    ) -> list[str]:
        """List all asserted fact_ids in the current scope, derived from RDF.

        Runs a lightweight SPARQL SELECT DISTINCT over ``asserted_data``
        member graphs to enumerate ``(subject, predicate, object, graph)``
        tuples, then computes ``fact_id`` (4-tuple sha256) for each using
        the canonical ``compute_fact_id`` algorithm so the result matches
        the write side (``FactEvidenceBindingModel.fact_id``).
        """
        asserted_iris = [
            m.graph_iri for m in scope.members if m.role == "asserted_data"
        ]
        if not asserted_iris:
            return []
        sparql = (
            "# phase3 asserted fact_id enumeration\n"
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            "SELECT DISTINCT ?s ?p ?o ?g WHERE {\n"
            "  VALUES ?g { {graph_iris} }\n"
            "  GRAPH ?g {\n"
            "    ?s ?p ?o .\n"
            "    FILTER(?p != rdf:type)\n"
            "    FILTER(?p != rdfs:label)\n"
            "  }\n"
            "}\n"
            "LIMIT {limit}"
        )
        values = " ".join(f"<{i}>" for i in asserted_iris)
        query = (
            sparql.replace("{graph_iris}", values).replace("{limit}", str(limit))
        )
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=asserted_iris,
            timeout_seconds=self.timeout_seconds,
            limit=limit,
        )
        fact_ids: list[str] = []
        for row in self._rows(result):
            s = self._cell(row, "s") or ""
            p = self._cell(row, "p") or ""
            o_value = self._cell(row, "o") or ""
            g = self._cell(row, "g") or ""
            if not (s and p and o_value and g):
                continue
            is_iri = self._cell_is_uri(row, "o")
            o_datatype = self._cell_datatype(row, "o") if not is_iri else None
            o_lang = self._cell_lang(row, "o") if not is_iri else None
            o_term = canonical_object_term(
                o_value, is_iri=is_iri, datatype=o_datatype, lang=o_lang
            )
            fact_ids.append(compute_fact_id(s, p, o_term, g))
        return fact_ids

    # ------------------------------------------------------------------
    # publication-readiness composer (Stage 3 §4.1)
    # ------------------------------------------------------------------

    def _compose_publication_readiness(
        self, scope: ScopeResolution, field_set: str
    ) -> dict[str, Any]:
        """Aggregate staleness, missing-evidence, open edits, projection
        freshness and editability into a single readiness row. See spec §4.1
        for the field contract."""
        staleness_row = self._compose_graph_set_staleness(scope, "detail")
        missing = self._missing_evidence_count(scope)
        open_edits = self._open_edits_count(scope.graph_set_id)
        editable_graphs = [
            {"graph_iri": m.graph_iri, "role": m.role}
            for m in scope.members
            if m.editable
        ]
        projection_freshness = self._projection_freshness(scope.graph_set_id)
        gates = self._evaluate_publication_gates(
            staleness_row=staleness_row,
            missing_evidence=missing,
            open_edits=open_edits,
            projection_freshness=projection_freshness,
        )
        ready = all(g["status"] == "passed" for g in gates)
        row: dict[str, Any] = {
            "graph_set_id": scope.graph_set_id,
            "ready": ready,
            "gates": gates,
            "blockers": [g["label"] for g in gates if g["status"] == "blocked"],
            "warnings": [g["label"] for g in gates if g["status"] == "warning"],
            "editable_graph_count": len(editable_graphs),
            "editable_graphs": editable_graphs,
            "last_published_at": self._last_published_at(scope.graph_set_id),
        }
        if field_set == "summary":
            return {
                "graph_set_id": row["graph_set_id"],
                "ready": row["ready"],
                "blockers": row["blockers"],
                "warnings": row["warnings"],
            }
        return row

    def _open_edits_count(self, graph_set_id: str) -> int:
        """Stage 3 publication blocker: count SemanticEditAuditModel rows
        whose latest edit per target graph is still unapplied (``applied``
        flag False). Only the latest edit per target graph is considered so
        that an applied-then-reopened graph counts once."""
        if self.session is None:
            return 0
        from sqlalchemy import func, select

        from app.repositories.models import (
            SemanticEditAuditModel,
            SemanticGraphSetMemberModel,
        )

        member_iris = list(
            self.session.scalars(
                select(SemanticGraphSetMemberModel.graph_iri).where(
                    SemanticGraphSetMemberModel.graph_set_id == graph_set_id
                )
            )
        )
        if not member_iris:
            return 0
        latest_subq = (
            select(
                SemanticEditAuditModel.target_graph_iri,
                func.max(SemanticEditAuditModel.created_at).label("max_created_at"),
            )
            .where(SemanticEditAuditModel.target_graph_iri.in_(member_iris))
            .group_by(SemanticEditAuditModel.target_graph_iri)
            .subquery()
        )
        rows = list(
            self.session.scalars(
                select(SemanticEditAuditModel).join(
                    latest_subq,
                    (
                        SemanticEditAuditModel.target_graph_iri
                        == latest_subq.c.target_graph_iri
                    )
                    & (
                        SemanticEditAuditModel.created_at
                        == latest_subq.c.max_created_at
                    ),
                )
            )
        )
        return sum(1 for r in rows if not r.applied)

    def _projection_freshness(self, graph_set_id: str) -> dict[str, dict[str, Any]]:
        """Returns {manifest_projection_kind: {fresh, last_run_at}}."""
        if self.session is None:
            return {}
        from sqlalchemy import select

        from app.repositories.models import SemanticProjectionManifestModel

        rows = list(
            self.session.scalars(
                select(SemanticProjectionManifestModel).where(
                    SemanticProjectionManifestModel.graph_set_id == graph_set_id
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

    def _last_published_at(self, graph_set_id: str) -> str | None:
        if self.session is None:
            return None
        from sqlalchemy import select

        from app.repositories.models import SemanticGraphSetModel

        row = self.session.scalar(
            select(SemanticGraphSetModel).where(
                SemanticGraphSetModel.id == graph_set_id
            )
        )
        if row and row.graph_set_metadata:
            v = row.graph_set_metadata.get("last_published_at")
            return str(v) if v else None
        return None

    def _evaluate_publication_gates(
        self,
        *,
        staleness_row: dict[str, Any],
        missing_evidence: int,
        open_edits: int,
        projection_freshness: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Map staleness/missing-evidence/open-edits/projection signals to
        the §4.1 ``GateStatus`` shape."""
        gates: list[dict[str, Any]] = []
        members = staleness_row.get("members", []) if staleness_row else []
        for kind in ("validation", "reasoning", "rule"):
            # Each member of a graph set shares the same derived pointer; we
            # pick the first member whose derived_state carries this kind.
            state: Any = None
            for member in members:
                derived = member.get("derived_state") or {}
                if kind in derived:
                    state = derived[kind]
                    break
            # Fall back to the per-member boolean flag (e.g. ``validation_stale``).
            stale_flag = None
            for member in members:
                key = f"{kind}_stale"
                if key in member and member[key] is not None:
                    stale_flag = member[key]
                    break
            if state is None and stale_flag is None:
                gate_status = "blocked"
                label_state = "unknown"
            elif (isinstance(state, dict) and state.get("status") == "stale") or stale_flag:
                gate_status = "warning"
                label_state = "stale"
            else:
                gate_status = "passed"
                label_state = "fresh"
            gates.append({
                "gate": f"{kind}_stale",
                "status": gate_status,
                "details": {
                    "staleness_state": label_state,
                    "latest_run_id": (
                        state.get("run_id") if isinstance(state, dict) else None
                    ),
                },
                "label": f"{kind} is {label_state}",
            })
        gates.append({
            "gate": "missing_evidence",
            "status": "passed" if missing_evidence == 0 else "blocked",
            "details": {"count": missing_evidence},
            "label": f"{missing_evidence} facts missing evidence",
        })
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
    # graph-set-history-list composer (Stage 3 §4.2)
    # ------------------------------------------------------------------

    def _member_editable(self, graph_iri: str) -> bool:
        """Stage 3 history-list helper: read the graph registry row for
        ``graph_iri`` and return its ``mutable_by_direct_edit`` flag, defaulting
        to True when the row is absent (matches the scope resolver's behaviour)."""
        from sqlalchemy import select

        from app.repositories.models import SemanticGraphRegistryModel

        row = self.session.scalar(
            select(SemanticGraphRegistryModel).where(
                SemanticGraphRegistryModel.graph_iri == graph_iri
            )
        )
        if row is None:
            return True
        return bool(row.mutable_by_direct_edit)

    def _compose_graph_set_history_list(
        self, scope: ScopeResolution
    ) -> dict[str, Any]:
        """List graph sets in the same scope as ``scope.graph_set_id``."""
        if self.session is None:
            return {"graph_sets": [], "total": 0}
        from sqlalchemy import func, select

        from app.repositories.models import (
            SemanticDerivedResultPointerModel,
            SemanticGraphSetMemberModel,
            SemanticGraphSetModel,
        )

        anchor = self.session.scalar(
            select(SemanticGraphSetModel).where(
                SemanticGraphSetModel.id == scope.graph_set_id
            )
        )
        if anchor is None:
            return {"graph_sets": [], "total": 0}
        sets = list(
            self.session.scalars(
                select(SemanticGraphSetModel)
                .where(
                    SemanticGraphSetModel.scope_type == anchor.scope_type,
                    SemanticGraphSetModel.scope_id == anchor.scope_id,
                )
                .order_by(SemanticGraphSetModel.created_at.desc())
            )
        )
        out: list[dict[str, Any]] = []
        for s in sets:
            members = list(
                self.session.scalars(
                    select(SemanticGraphSetMemberModel).where(
                        SemanticGraphSetMemberModel.graph_set_id == s.id
                    )
                )
            )
            any_editable = any(self._member_editable(m.graph_iri) for m in members)
            latest_pointer = self.session.scalar(
                select(
                    func.max(SemanticDerivedResultPointerModel.became_current_at)
                )
                .join(
                    SemanticGraphSetMemberModel,
                    SemanticGraphSetMemberModel.graph_iri
                    == SemanticDerivedResultPointerModel.result_graph_iri,
                )
                .where(SemanticGraphSetMemberModel.graph_set_id == s.id)
            )
            metadata = s.graph_set_metadata or {}
            out.append({
                "graph_set_id": s.id,
                "status": "editable" if any_editable else "locked",
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "locked_at": metadata.get("locked_at"),
                "source_signature": s.source_signature,
                "member_count": len(members),
                "latest_derived_pointer_at": (
                    latest_pointer.isoformat() if latest_pointer else None
                ),
                "ready": None,
            })
        return {"graph_sets": out, "total": len(out)}

    # ------------------------------------------------------------------
    # graph-set-delta composer (Stage 3 §4.3)
    # ------------------------------------------------------------------

    def _compose_graph_set_delta(
        self,
        scope: ScopeResolution,
        target: str | None,
        limit: int,
    ) -> dict[str, Any]:
        """Diff two graph sets by named graph role."""
        if not target:
            raise ReadModelError(
                "graph-set-delta requires ?target=<other_graph_set_id>"
            )
        if self.session is None:
            raise ReadModelError(
                "graph-set-delta requires a database session for scope resolution"
            )
        from sqlalchemy import select

        from app.repositories.models import SemanticGraphSetMemberModel

        def _members_for(graph_set_id: str) -> list[SemanticGraphSetMemberModel]:
            return list(
                self.session.scalars(
                    select(SemanticGraphSetMemberModel).where(
                        SemanticGraphSetMemberModel.graph_set_id == graph_set_id
                    )
                )
            )

        base_members = {m.role: m for m in _members_for(scope.graph_set_id)}
        target_members = {m.role: m for m in _members_for(target)}
        roles = sorted(set(base_members) | set(target_members))
        out: list[dict[str, Any]] = []
        for role in roles:
            b = base_members.get(role)
            t = target_members.get(role)
            # Fetch the FULL triple sets per role (uncapped) so set differences
            # reflect the real diff size. The ``limit`` only slices the
            # displayed ``added[]``/``removed[]`` arrays in the response.
            b_triples = self._role_triples(b.graph_iri) if b else set()
            t_triples = self._role_triples(t.graph_iri) if t else set()
            added_full = list(t_triples - b_triples)
            removed_full = list(b_triples - t_triples)
            out.append({
                "role": role,
                "base_graph_iri": b.graph_iri if b else None,
                "target_graph_iri": t.graph_iri if t else None,
                "added": [self._triple_dict(x) for x in added_full[:limit]],
                "removed": [self._triple_dict(x) for x in removed_full[:limit]],
                "counts": {
                    "added": len(added_full),
                    "removed": len(removed_full),
                },
            })
        truncated = any(
            r["counts"]["added"] > limit or r["counts"]["removed"] > limit
            for r in out
        )
        return {
            "base_graph_set_id": scope.graph_set_id,
            "target_graph_set_id": target,
            "roles": out,
            "truncated": truncated,
        }

    def _role_triples(self, graph_iri: str) -> set[tuple[str, str, str]]:
        """Return the FULL set of (s, p, o) tuples in ``graph_iri``.

        Stage 3 §4.3 requires the diff to be computed over the uncapped
        triple sets so ``counts.added`` / ``counts.removed`` reflect the
        real diff size; the ``limit`` only slices the response arrays in
        the composer. A separate ``SELECT COUNT`` query is unnecessary
        here because we materialize the full set anyway to compute the
        set difference.
        """
        # Use a large cap to protect against pathological graphs while
        # remaining effectively unbounded for any realistic ontology. The
        # composer slices to ``limit`` afterwards.
        fetch_limit = 100_000
        query = (
            f"# graph-set-delta SELECT\nSELECT ?s ?p ?o WHERE {{ "
            f"GRAPH <{graph_iri}> {{ ?s ?p ?o }} }} LIMIT {fetch_limit}"
        )
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=[graph_iri],
            timeout_seconds=self.timeout_seconds,
            limit=fetch_limit,
        )
        rows = self._rows(result)
        triples: set[tuple[str, str, str]] = set()
        for row in rows:
            s = self._cell(row, "s") or self._cell(row, "subject") or ""
            p = self._cell(row, "p") or self._cell(row, "predicate") or ""
            o = self._cell(row, "o") or self._cell(row, "object") or ""
            triples.add((s, p, o))
        return triples

    @staticmethod
    def _triple_dict(triple: tuple[str, str, str]) -> dict[str, str]:
        s, p, o = triple
        return {"subject": s, "predicate": p, "object": o}

    # ------------------------------------------------------------------
    # fact-audit-queue composer (Stage 2 §6.3)
    # ------------------------------------------------------------------

    _FACT_KINDS = ("asserted", "inferred", "rule_derived", "missing_evidence")

    def _compose_fact_audit_queue(
        self,
        scope: ScopeResolution,
        kind: str | None,
        field_set: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Compose the FactAuditPage queue by ``?kind=``.

        kind selects the source graph(s):

        - ``asserted`` / ``missing_evidence`` → asserted_data members of the
          active graph set. ``missing_evidence`` additionally filters rows to
          those whose subject carries ``op:evidenceStatus "missing_evidence"``.
        - ``inferred`` → effective reasoning-result graph.
        - ``rule_derived`` → effective rule-result graph.

        Each row is decorated into the unified FactRow shape (spec §6.3):
        id, assertion_kind, subject_iri, subject_label, predicate_iri,
        predicate_label, object_value, object_label, graph_iri,
        evidence_status, audit_status, derived_from (when applicable),
        stale, stale_reason.
        """
        resolved_kind = (kind or "asserted").strip()
        if resolved_kind not in self._FACT_KINDS:
            raise ReadModelError(
                f"Unsupported fact-audit-queue kind: {resolved_kind}. "
                f"Must be one of: {', '.join(self._FACT_KINDS)}"
            )

        warnings: list[dict[str, str]] = list(scope.warnings)
        attach_evidence = field_set == "evidence"

        if resolved_kind in {"asserted", "missing_evidence"}:
            data_iris = [
                m.graph_iri for m in scope.members if m.role == "asserted_data"
            ]
            if not data_iris:
                return [], warnings + [
                    {
                        "code": "fact_audit_no_asserted_data",
                        "message": "Graph set is missing an asserted data graph.",
                    }
                ]
            # Phase 3: enumerate every asserted fact via the unified
            # ``fact-audit-queue`` template, then derive missing_evidence
            # status from PG (the legacy ``missing-evidence-list`` SPARQL
            # template was removed in Phase 4 cleanup).
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
            items = self._apply_evidence_bindings(items)
            if resolved_kind == "missing_evidence":
                items = [
                    it for it in items
                    if it["evidence_status"] == "missing_evidence"
                ]
            if not attach_evidence:
                for it in items:
                    it["evidence_bindings"] = []
            return items, warnings

        if resolved_kind == "inferred":
            reasoning_iri = scope.reasoning_result_graph_iri
            if not reasoning_iri:
                if any(w.get("code") == "missing_reasoning_result" for w in warnings):
                    return [], warnings
                return [], warnings + [
                    {
                        "code": "fact_audit_no_inferred_pointer",
                        "message": (
                            "No effective reasoning-result pointer. Click "
                            "Generate to run reasoning."
                        ),
                    }
                ]
            rows = self._fetch_fact_rows(
                [reasoning_iri], template_name="fact-audit-queue"
            )
            stale = self._is_stale(reasoning_iri, scope)
            stale_reason = self._staleness_reason(reasoning_iri, scope)
            run_id = (
                scope.derived_state.get("reasoning", {}).get("run_id")
                if scope.derived_state
                else None
            )
            items = [
                self._decorate_fact_row(
                    row,
                    assertion_kind="inferred",
                    scope=scope,
                    derived_run_id=run_id,
                    stale=stale,
                    stale_reason=stale_reason,
                )
                for row in rows
            ]
            items = self._apply_evidence_bindings(items)
            if not attach_evidence:
                for it in items:
                    it["evidence_bindings"] = []
            return items, warnings

        # rule_derived
        rule_iri = scope.rule_result_graph_iri
        if not rule_iri:
            if any(w.get("code") == "missing_rule_result" for w in warnings):
                return [], warnings
            return [], warnings + [
                {
                    "code": "fact_audit_no_rule_pointer",
                    "message": (
                        "No effective rule-result pointer. Click Run rules "
                        "to execute rule definitions."
                    ),
                }
            ]
        rows = self._fetch_fact_rows([rule_iri], template_name="fact-audit-queue")
        stale = self._is_stale(rule_iri, scope)
        stale_reason = self._staleness_reason(rule_iri, scope)
        run_id = (
            scope.derived_state.get("rule", {}).get("run_id")
            if scope.derived_state
            else None
        )
        items = [
            self._decorate_fact_row(
                row,
                assertion_kind="rule_derived",
                scope=scope,
                derived_run_id=run_id,
                stale=stale,
                stale_reason=stale_reason,
            )
            for row in rows
        ]
        items = self._apply_evidence_bindings(items)
        if not attach_evidence:
            for it in items:
                it["evidence_bindings"] = []
        return items, warnings

    def _apply_evidence_bindings(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Batch-fetch evidence bindings from PG and populate each item.

        ``evidence_status`` is derived from whether any binding exists for
        the row's ``fact_id``. When the service has no SQLAlchemy session
        (legacy test wiring), each row falls back to ``missing_evidence``
        with empty bindings.
        """
        if self.session is None:
            for it in items:
                it.setdefault("evidence_bindings", [])
            return items
        fact_ids = [it["fact_id"] for it in items if it.get("fact_id")]
        bindings_by_fact = self._fetch_evidence_bindings_from_pg(
            fact_ids, self.session
        )
        for it in items:
            fid = it.get("fact_id") or ""
            bindings = bindings_by_fact.get(fid, [])
            it["evidence_bindings"] = bindings
            it["evidence_status"] = "with_evidence" if bindings else "missing_evidence"
        return items

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
        return self._apply_evidence_bindings(items)

    def _fetch_fact_rows(
        self,
        graph_iris: list[str],
        template_name: str,
        *,
        entity_iri: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Run the fact-audit-queue / missing-evidence template against the
        given source graphs and return raw SPARQL rows."""
        if not graph_iris:
            return []
        template = get_template(template_name)
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        query = self._compile_template_query(
            template,
            graph_iris,
            bounded_limit,
            entity_iri=entity_iri,
        )
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=graph_iris,
            timeout_seconds=self.timeout_seconds,
            limit=bounded_limit,
        )
        return list(self._rows(result))

    def _decorate_fact_row(
        self,
        row: dict[str, Any],
        *,
        assertion_kind: str,
        scope: ScopeResolution,
        bindings_by_fact: dict[str, list[dict[str, Any]]] | None = None,
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
        source_graph_iri = self._cell(row, "graph") or (
            scope.source_graph_iris[0] if scope.source_graph_iris else ""
        )
        # Audit status defaults to "pending" — the FactAuditPage surfaces
        # the audit_status that may be set on the row by an RDF-star
        # reification in a later iteration; absent that, everything is
        # pending review.
        audit_status = self._cell(row, "audit_status") or "pending"
        # Stable id: 4-tuple sha256 from ``compute_fact_id`` (matches the
        # write side and the fact_evidence_bindings table). Must preserve
        # datatype/lang so typed and lang-tagged literals hash the same as
        # the write path (compile_bind_fact_evidence).
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
            subject_iri, predicate_iri, object_term, source_graph_iri
        )
        # Phase 3: evidence_status is now derived from PG bindings rather
        # than from an op:evidenceStatus SPARQL marker. When the decorator
        # is called before bindings are fetched (e.g. inside
        # _compose_fact_audit_queue's first pass), ``bindings_by_fact`` is
        # None and the field is left to be filled in by the caller.
        if bindings_by_fact is not None:
            bindings = bindings_by_fact.get(fact_id, [])
            evidence_status = "with_evidence" if bindings else "missing_evidence"
        else:
            bindings = []
            # Preserve the legacy missing_evidence kind hint so the
            # composer's second pass can still classify rows before the PG
            # lookup. After the lookup the value will be overridden.
            evidence_status = "missing_evidence" if assertion_kind == "missing_evidence" else "with_evidence"
        # Staleness for derived graphs.
        if stale is None:
            stale_bool = self._is_stale(source_graph_iri, scope)
        else:
            stale_bool = bool(stale)
        if stale_reason is None:
            stale_reason_val = self._staleness_reason(source_graph_iri, scope)
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
            "graph_iri": source_graph_iri,
            "source_graph_iri": source_graph_iri,
            "evidence_status": evidence_status,
            "evidence_bindings": bindings,
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
    ) -> list[dict[str, Any]]:
        """Run the entity-search SPARQL against the active scope's data graphs,
        decorating each row with the standard decorator plus the
        ``comment`` / ``class_iri`` / ``class_label`` / ``graph_set_id``
        extensions declared in spec §4.1."""
        graph_iris = list(scope.source_graph_iris) or []
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        body = template.body
        body = body.replace("{graph_iris}", " ".join(f"<{i}>" for i in graph_iris))
        body = body.replace("{limit}", str(bounded_limit))
        # Bind the search substring ?q as a literal. Defaulting to the empty
        # string makes the FILTER a no-op so the same template can serve an
        # unfiltered listing call. A comment marker is appended so test fakes
        # can extract the value without parsing SPARQL.
        bound_q = q if q is not None else ""
        body = body.replace("?q", f'"{bound_q}"')
        body = body + f"\n# q_filter: \"{bound_q}\""
        # Bind the class filter in place. A VALUES preamble before PREFIX
        # declarations makes Oxigraph parse the query as malformed, so keep
        # the query prologue intact and rewrite only the filter expression.
        class_filter_expr = "FILTER(!BOUND(?class_iri) || ?class = ?class_iri)"
        if class_iri is not None:
            body = body.replace(class_filter_expr, f"FILTER(?class = <{class_iri}>)")
            body = body + f"\n# class_iri_filter: <{class_iri}>"
        result = self.rdf_store.query_read_model(
            query=body,
            graph_iris=graph_iris,
            timeout_seconds=self.timeout_seconds,
            limit=bounded_limit,
        )
        items: list[dict[str, Any]] = []
        for row in self._rows(result):
            decorated = self._decorate_row(row, scope, template)
            # Stage 4 §4.1 additional fields not provided by the base decorator.
            decorated["comment"] = self._cell(row, "comment")
            decorated["class_iri"] = self._cell(row, "class")
            decorated["class_label"] = self._cell(row, "class_label")
            decorated["graph_set_id"] = scope.graph_set_id
            items.append(decorated)
        return items

    # ------------------------------------------------------------------
    # agent-test-context composer (Stage 4 §4.2)
    # ------------------------------------------------------------------

    def _compose_agent_test_context(
        self,
        template: ReadModelTemplate,
        scope: ScopeResolution,
        *,
        q: str | None,
        limit: int,
        field_set: str,
    ) -> list[dict[str, Any]]:
        """Thin wrapper over ``_compose_entity_search`` that projects a
        smaller field set for the AgentTestService pre-LLM retrieval.

        The underlying SPARQL is the agent-test-context template body
        (no ``comment`` projection). The composed rows still carry the
        decorator's full envelope fields; downstream consumers simply
        read a subset."""
        items = self._compose_entity_search(
            template,
            scope,
            q=q,
            class_iri=None,
            limit=limit,
            field_set="agent",
        )
        # Strip the comment field for the agent projection.
        for item in items:
            item.pop("comment", None)
        return items

    # ------------------------------------------------------------------
    # owl-consistency-summary composer (Stage 4 §4.3)
    # ------------------------------------------------------------------

    def _compose_owl_consistency_summary(
        self, scope: ScopeResolution, field_set: str
    ) -> dict[str, Any]:
        """Project the latest consistency-classified reasoning run for the
        graph set into the spec §4.3 summary row."""
        if self.session is None:
            return {
                "graph_set_id": scope.graph_set_id,
                "run_id": None,
                "consistent": None,
                "classification": {},
                "entailment_count": 0,
                "unsatisfiable_classes": [],
                "result_graph_iri": None,
                "started_at": None,
                "finished_at": None,
                "is_stale": False,
            }
        from sqlalchemy import select

        from app.repositories.models import SemanticReasoningRunModel

        # Find the latest reasoning run whose run_metadata['tasks'] contains
        # "consistency" and whose result graph (or source graphs) overlaps
        # the active graph set members. We filter in Python because the JSONB
        # containment operator is dialect-specific; the run table is small
        # per graph set.
        member_iris = {m.graph_iri for m in scope.members}
        rows = list(
            self.session.scalars(
                select(SemanticReasoningRunModel)
                .order_by(SemanticReasoningRunModel.started_at.desc())
            )
        )
        run: SemanticReasoningRunModel | None = None
        for r in rows:
            metadata = r.run_metadata or {}
            tasks = metadata.get("tasks") or []
            if "consistency" not in tasks:
                continue
            source_set = set(r.source_graph_iris or [])
            if r.result_graph_iri:
                source_set.add(r.result_graph_iri)
            if not member_iris or (source_set & member_iris):
                run = r
                break
        if run is None:
            return {
                "graph_set_id": scope.graph_set_id,
                "run_id": None,
                "consistent": None,
                "classification": {},
                "entailment_count": 0,
                "unsatisfiable_classes": [],
                "result_graph_iri": None,
                "started_at": None,
                "finished_at": None,
                "is_stale": False,
            }
        metadata = run.run_metadata or {}
        entailments = metadata.get("entailments") or []
        unsatisfiable = [
            e.get("subject") or e.get("iri") or ""
            for e in entailments
            if isinstance(e, dict)
            and (
                "unsatisfiable" in str(e.get("predicate", "")).lower()
                or "unsatisfiable" in str(e.get("classification", "")).lower()
            )
        ]
        # Staleness: reuse the graph-set staleness helper. A run is stale if
        # any member graph has been edited since the run finished.
        staleness_row = self._compose_graph_set_staleness(scope, "summary")
        latest_edit_raw = staleness_row.get("last_semantic_edit_at")
        is_stale = False
        if run.finished_at is not None and latest_edit_raw is not None:
            try:
                from datetime import datetime

                edited_at = datetime.fromisoformat(latest_edit_raw)
                if edited_at.tzinfo is None:
                    from datetime import timezone

                    edited_at = edited_at.replace(tzinfo=timezone.utc)
                run_finished = run.finished_at
                if run_finished.tzinfo is None:
                    from datetime import timezone

                    run_finished = run_finished.replace(tzinfo=timezone.utc)
                is_stale = edited_at > run_finished
            except (ValueError, TypeError):
                is_stale = False
        return {
            "graph_set_id": scope.graph_set_id,
            "run_id": run.id,
            "consistent": run.consistent,
            "classification": metadata.get("classification") or {},
            "entailment_count": len(entailments),
            "unsatisfiable_classes": unsatisfiable,
            "result_graph_iri": run.result_graph_iri,
            "started_at": (
                run.started_at.isoformat() if run.started_at else None
            ),
            "finished_at": (
                run.finished_at.isoformat() if run.finished_at else None
            ),
            "is_stale": is_stale,
        }


def _sparql_iri_value(value: str) -> str:
    """Validate an IRI string before embedding it between SPARQL angle brackets."""
    stripped = value.strip()
    if not stripped or any(ch in stripped for ch in "<> \t\r\n"):
        raise ReadModelError("Invalid entity IRI")
    return stripped
