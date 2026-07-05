"""Graph-set service: explicit lists of source/governance/derived graphs.

A graph set represents the working version used by a query, validation run,
projection, or product view. Phase 4 stores graph-set membership in Postgres
and computes a deterministic source signature from members and source-graph
revisions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.services.semantic_graph_registry import (
    GraphClassification,
    GraphRegistryError,
    graph_set_signature,
)


class GraphSetError(RuntimeError):
    status_code = 400


class GraphSetNotFound(GraphSetError):
    status_code = 404


class SemanticGraphSetService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def create_graph_set(
        self,
        name: str,
        scope_type: str,
        scope_id: str | None,
        members: list[dict[str, Any]],
        created_by: str | None = None,
        metadata: dict[str, Any] | None = None,
        supersedes: str | None = None,
    ) -> SemanticGraphSetModel:
        if not name:
            raise GraphSetError("Graph set name is required")
        if not members:
            raise GraphSetError("Graph set requires at least one member")
        graph_set = SemanticGraphSetModel(
            id=str(uuid4()),
            name=name,
            scope_type=scope_type,
            scope_id=scope_id,
            status="active",
            source_signature="",
            created_by=created_by,
            graph_set_metadata=metadata or {},
        )
        self.session.add(graph_set)
        for index, member in enumerate(members):
            self._validate_member(member)
            graph_set.members.append(
                SemanticGraphSetMemberModel(
                    id=str(uuid4()),
                    graph_iri=member["graph_iri"],
                    role=member["role"],
                    required=bool(member.get("required", True)),
                    sort_order=int(member.get("sort_order", index)),
                    member_metadata=member.get("metadata", {}),
                )
            )
        if supersedes:
            self._mark_superseded(supersedes)
        graph_set.source_signature = self._compute_signature(graph_set)
        self.session.commit()
        return graph_set

    def update_membership(
        self,
        graph_set_id: str,
        members: list[dict[str, Any]],
    ) -> SemanticGraphSetModel:
        graph_set = self.get_graph_set(graph_set_id)
        for member in graph_set.members:
            self.session.delete(member)
        self.session.flush()
        graph_set.members = []
        for index, member in enumerate(members):
            self._validate_member(member)
            graph_set.members.append(
                SemanticGraphSetMemberModel(
                    id=str(uuid4()),
                    graph_iri=member["graph_iri"],
                    role=member["role"],
                    required=bool(member.get("required", True)),
                    sort_order=int(member.get("sort_order", index)),
                    member_metadata=member.get("metadata", {}),
                )
            )
        graph_set.source_signature = self._compute_signature(graph_set)
        self._mark_dependent_pointers_stale(graph_set_id)
        self.session.commit()
        return graph_set

    def get_graph_set(self, graph_set_id: str) -> SemanticGraphSetModel:
        record = self.session.scalar(
            select(SemanticGraphSetModel).where(SemanticGraphSetModel.id == graph_set_id)
        )
        if record is None:
            raise GraphSetNotFound(f"Graph set not found: {graph_set_id}")
        return record

    def list_graph_sets(
        self,
        scope_type: str | None = None,
        scope_id: str | None = None,
        status: str | None = None,
    ) -> list[SemanticGraphSetModel]:
        statement = select(SemanticGraphSetModel).order_by(
            SemanticGraphSetModel.created_at.desc()
        )
        if scope_type:
            statement = statement.where(SemanticGraphSetModel.scope_type == scope_type)
        if scope_id:
            statement = statement.where(SemanticGraphSetModel.scope_id == scope_id)
        if status:
            statement = statement.where(SemanticGraphSetModel.status == status)
        return list(self.session.scalars(statement))

    def describe(self, graph_set_id: str) -> dict[str, Any]:
        graph_set = self.get_graph_set(graph_set_id)
        revisions = self._revisions_for(graph_set)
        return {
            "id": graph_set.id,
            "name": graph_set.name,
            "scope_type": graph_set.scope_type,
            "scope_id": graph_set.scope_id,
            "status": graph_set.status,
            "source_signature": graph_set.source_signature,
            "created_by": graph_set.created_by,
            "members": [
                {
                    "graph_iri": member.graph_iri,
                    "role": member.role,
                    "required": member.required,
                    "sort_order": member.sort_order,
                    "metadata": member.member_metadata,
                    "revision": revisions.get(member.graph_iri, 0),
                }
                for member in graph_set.members
            ],
            "current_pointers": self._current_pointers(graph_set_id),
            "metadata": graph_set.graph_set_metadata or {},
        }

    def source_signature_for(self, graph_set_id: str) -> str:
        graph_set = self.get_graph_set(graph_set_id)
        return self._compute_signature(graph_set)

    def _compute_signature(self, graph_set: SemanticGraphSetModel) -> str:
        members_sorted = sorted(
            (
                (member.graph_iri, member.role, member.sort_order)
                for member in graph_set.members
            ),
            key=lambda item: (item[2], item[0]),
        )
        revisions = self._revisions_for(graph_set)
        return graph_set_signature(members_sorted, revisions)

    def _revisions_for(self, graph_set: SemanticGraphSetModel) -> dict[str, int]:
        graph_iris = [member.graph_iri for member in graph_set.members]
        if not graph_iris:
            return {}
        rows = self.session.scalars(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri.in_(graph_iris)
            )
        )
        return {row.graph_iri: row.revision for row in rows}

    def _current_pointers(self, graph_set_id: str) -> list[dict[str, Any]]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel)
            .where(SemanticDerivedResultPointerModel.graph_set_id == graph_set_id)
            .order_by(SemanticDerivedResultPointerModel.result_kind)
        )
        return [
            {
                "result_kind": row.result_kind,
                "run_id": row.run_id,
                "result_graph_iri": row.result_graph_iri,
                "status": row.status,
                "engine_name": row.engine_name,
                "engine_version": row.engine_version,
                "rule_version": row.rule_version,
                "shape_version": row.shape_version,
                "became_current_at": row.became_current_at,
            }
            for row in rows
        ]

    def _mark_dependent_pointers_stale(self, graph_set_id: str) -> None:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.graph_set_id == graph_set_id,
                SemanticDerivedResultPointerModel.status == "current",
            )
        )
        for row in rows:
            row.status = "stale"
            row.pointer_metadata = {
                **(row.pointer_metadata or {}),
                "stale_reason": "graph_set_membership_changed",
                "stale_at": datetime.now(UTC).isoformat(),
            }

    def _mark_superseded(self, graph_set_id: str) -> None:
        prior = self.session.scalar(
            select(SemanticGraphSetModel).where(SemanticGraphSetModel.id == graph_set_id)
        )
        if prior is None:
            return
        prior.status = "superseded"

    def _validate_member(self, member: dict[str, Any]) -> None:
        if "graph_iri" not in member:
            raise GraphSetError("Graph set member requires graph_iri")
        if "role" not in member:
            raise GraphSetError("Graph set member requires role")
        if not member["graph_iri"].startswith(self.settings.semantic_graph_iri_prefix):
            raise GraphSetError(
                f"Graph set member IRI is outside the managed prefix: {member['graph_iri']}"
            )
        classifier = GraphClassification(self.settings.semantic_graph_iri_prefix)
        classifier.classify(member["graph_iri"])


def stale_reason_for_membership_change() -> str:
    return "graph_set_membership_changed"
