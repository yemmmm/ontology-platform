"""Resolve a graph set + include parameter into concrete graph IRIs and derived state.

Phase 6 read APIs and projections use this resolver to turn an `include`
parameter (`asserted`, `asserted-plus-reasoning`, `asserted-plus-rules`,
`full-working-view`) into the source-graph IRIs, governance IRIs, derived-result
graph IRIs, derived-state descriptor, and warnings for a single graph set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticEditAuditModel,
    SemanticGraphRegistryModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)


class ReadScopeError(RuntimeError):
    status_code = 400


_VALID_INCLUDES = {
    "asserted",
    "asserted-plus-reasoning",
    "asserted-plus-rules",
    "full-working-view",
}

_SOURCE_ROLES = {"asserted_ontology", "asserted_data"}
_GOVERNANCE_ROLES = {"evidence", "policy"}


@dataclass
class ScopeMember:
    """Per-member data for graph-set-staleness and similar read models."""

    graph_iri: str
    role: str
    editable: bool = True
    last_edit_at: datetime | None = None
    derived_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScopeResolution:
    graph_set_id: str
    source_signature: str
    include: str
    source_graph_iris: list[str]
    shape_graph_iris: list[str]
    governance_graph_iris: list[str]
    reasoning_result_graph_iri: str | None
    rule_result_graph_iri: str | None
    derived_state: dict[str, Any]
    warnings: list[dict[str, str]] = field(default_factory=list)
    members: list[ScopeMember] = field(default_factory=list)


class SemanticReadScopeResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(
        self,
        graph_set_id: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
    ) -> ScopeResolution:
        if include not in _VALID_INCLUDES:
            raise ReadScopeError(f"Unsupported include value: {include}")
        graph_set = self._get_graph_set(graph_set_id)
        members = self._members(graph_set_id)
        source_iris = [m.graph_iri for m in members if m.role in _SOURCE_ROLES]
        shape_iris = [m.graph_iri for m in members if m.role == "shape"]
        governance_iris = [
            m.graph_iri for m in members if m.role in _GOVERNANCE_ROLES
        ]

        pointers = self._current_pointers(graph_set_id)
        warnings: list[dict[str, str]] = []
        reasoning_iri: str | None = None
        rule_iri: str | None = None

        if include in {"asserted-plus-reasoning", "full-working-view"}:
            reasoning_iri, warning = self._resolve_pointer(
                pointers, "reasoning", allow_stale_derived
            )
            if warning:
                warnings.append(warning)

        if include in {"asserted-plus-rules", "full-working-view"}:
            rule_iri, warning = self._resolve_pointer(
                pointers, "rule", allow_stale_derived
            )
            if warning:
                warnings.append(warning)

        derived_state = {
            "reasoning": self._derived_descriptor(pointers.get("reasoning")),
            "rule": self._derived_descriptor(pointers.get("rule")),
        }

        member_entries = self._build_members(members, pointers)

        return ScopeResolution(
            graph_set_id=graph_set_id,
            source_signature=graph_set.source_signature,
            include=include,
            source_graph_iris=source_iris,
            shape_graph_iris=shape_iris,
            governance_graph_iris=governance_iris,
            reasoning_result_graph_iri=reasoning_iri,
            rule_result_graph_iri=rule_iri,
            derived_state=derived_state,
            warnings=warnings,
            members=member_entries,
        )

    def _get_graph_set(self, graph_set_id: str) -> SemanticGraphSetModel:
        record = self.session.scalar(
            select(SemanticGraphSetModel).where(
                SemanticGraphSetModel.id == graph_set_id
            )
        )
        if record is None:
            raise ReadScopeError(f"Graph set not found: {graph_set_id}")
        return record

    def _members(self, graph_set_id: str) -> list[SemanticGraphSetMemberModel]:
        return list(
            self.session.scalars(
                select(SemanticGraphSetMemberModel)
                .where(SemanticGraphSetMemberModel.graph_set_id == graph_set_id)
                .order_by(SemanticGraphSetMemberModel.sort_order)
            )
        )

    def _current_pointers(
        self, graph_set_id: str
    ) -> dict[str, SemanticDerivedResultPointerModel]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.graph_set_id == graph_set_id
            )
        )
        return {row.result_kind: row for row in rows}

    def _resolve_pointer(
        self,
        pointers: dict[str, SemanticDerivedResultPointerModel],
        kind: str,
        allow_stale: bool,
    ) -> tuple[str | None, dict[str, str] | None]:
        pointer = pointers.get(kind)
        if pointer is None:
            return None, {
                "code": f"missing_{kind}_result",
                "message": f"No current {kind} result pointer.",
            }
        if pointer.status == "stale":
            if not allow_stale:
                raise ReadScopeError(
                    f"{kind} result pointer is stale for this graph set"
                )
            return pointer.result_graph_iri, {
                "code": f"stale_{kind}_result",
                "message": f"{kind.capitalize()}-derived statements are stale for this graph set.",
            }
        return pointer.result_graph_iri, None

    def _derived_descriptor(
        self, pointer: SemanticDerivedResultPointerModel | None
    ) -> dict[str, Any]:
        if pointer is None:
            return {"status": "missing", "run_id": None, "result_graph_iri": None}
        return {
            "status": pointer.status,
            "run_id": pointer.run_id,
            "result_graph_iri": pointer.result_graph_iri,
        }

    def _build_members(
        self,
        members: list[SemanticGraphSetMemberModel],
        pointers: dict[str, SemanticDerivedResultPointerModel],
    ) -> list[ScopeMember]:
        if not members:
            return []

        member_iris = [m.graph_iri for m in members]

        # Derive per-member derived_state from graph-set-level pointers.
        # All members of the same graph set share the same derived pointers.
        member_derived: dict[str, Any] = {}
        for kind, pointer in pointers.items():
            member_derived[kind] = {
                "status": pointer.status,
                "result_graph_iri": pointer.result_graph_iri,
                "became_current_at": pointer.became_current_at,
                "engine_name": pointer.engine_name,
                "engine_version": pointer.engine_version,
                "rule_version": pointer.rule_version,
                "shape_version": pointer.shape_version,
            }

        # Query registry for editable state.
        registry_rows = self.session.scalars(
            select(SemanticGraphRegistryModel).where(
                SemanticGraphRegistryModel.graph_iri.in_(member_iris)
            )
        ).all()
        registry_by_iri: dict[str, SemanticGraphRegistryModel] = {
            r.graph_iri: r for r in registry_rows
        }

        # Query latest semantic edit audit per member graph.
        latest_edits_subq = (
            select(
                SemanticEditAuditModel.target_graph_iri,
                func.max(SemanticEditAuditModel.created_at).label("max_created_at"),
            )
            .where(SemanticEditAuditModel.target_graph_iri.in_(member_iris))
            .group_by(SemanticEditAuditModel.target_graph_iri)
            .subquery()
        )
        edit_rows = self.session.scalars(
            select(SemanticEditAuditModel).join(
                latest_edits_subq,
                (SemanticEditAuditModel.target_graph_iri == latest_edits_subq.c.target_graph_iri)
                & (SemanticEditAuditModel.created_at == latest_edits_subq.c.max_created_at),
            )
        ).all()
        edit_by_iri: dict[str, SemanticEditAuditModel] = {
            e.target_graph_iri: e for e in edit_rows if e.target_graph_iri
        }

        result: list[ScopeMember] = []
        for m in members:
            registry = registry_by_iri.get(m.graph_iri)
            editable = registry.mutable_by_direct_edit if registry else True
            edit = edit_by_iri.get(m.graph_iri)
            last_edit_at = edit.created_at if edit else None
            result.append(
                ScopeMember(
                    graph_iri=m.graph_iri,
                    role=m.role,
                    editable=editable,
                    last_edit_at=last_edit_at,
                    derived_state=dict(member_derived),
                )
            )
        return result
