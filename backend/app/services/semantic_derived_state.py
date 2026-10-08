"""Shared source revisions and invalidation for projections and historical pointers."""

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
    SemanticProjectionManifestModel,
)


class SemanticRevisionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_revision(self, graph_iri: str) -> SemanticGraphRevisionModel | None:
        return self.session.scalar(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri == graph_iri
            )
        )

    def bump_revisions(
        self,
        graph_iris: list[str],
        audit_id: str | None = None,
        actor: str | None = None,
        content_hashes: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Increment revisions for each affected graph after a successful edit."""
        revisions: dict[str, int] = {}
        if not graph_iris:
            return revisions
        now = datetime.now(UTC)
        content_hashes = content_hashes or {}
        for graph_iri in graph_iris:
            record = self.get_revision(graph_iri)
            if record is None:
                record = SemanticGraphRevisionModel(
                    id=str(uuid4()),
                    graph_iri=graph_iri,
                    revision=1,
                    content_hash=content_hashes.get(graph_iri),
                    last_edit_audit_id=audit_id,
                    changed_at=now,
                    changed_by=actor,
                    revision_metadata=metadata or {},
                )
                self.session.add(record)
            else:
                record.revision = int(record.revision or 0) + 1
                record.changed_at = now
                record.changed_by = actor or record.changed_by
                record.last_edit_audit_id = audit_id or record.last_edit_audit_id
                if graph_iri in content_hashes:
                    record.content_hash = content_hashes[graph_iri]
                if metadata:
                    record.revision_metadata = {**(record.revision_metadata or {}), **metadata}
            revisions[graph_iri] = record.revision
        self.session.flush()
        return revisions


class SemanticDerivedStateService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings


    def mark_stale_after_edit(
        self,
        affected_graph_iris: list[str],
        audit_id: str | None = None,
        *,
        commit: bool = True,
    ) -> list[SemanticDerivedResultPointerModel]:
        if not affected_graph_iris:
            return []
        graph_set_ids = self._graph_sets_containing(affected_graph_iris)
        if not graph_set_ids:
            return []
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.graph_set_id.in_(graph_set_ids),
                SemanticDerivedResultPointerModel.status == "current",
            )
        )
        stale: list[SemanticDerivedResultPointerModel] = []
        now = datetime.now(UTC).isoformat()
        for row in rows:
            row.status = "stale"
            row.pointer_metadata = {
                **(row.pointer_metadata or {}),
                "stale_reason": "source_graph_revision_changed",
                "stale_at": now,
                "stale_audit_id": audit_id,
            }
            stale.append(row)
        self._mark_projection_manifests_stale(
            graph_set_ids,
            audit_id=audit_id,
            reason="source_graph_revision_changed",
            stale_at=now,
        )
        if commit:
            self.session.commit()
        return stale

    def mark_graph_set_stale(
        self,
        graph_set_id: str,
        *,
        audit_id: str | None = None,
        reason: str = "workspace_changed",
        commit: bool = True,
    ) -> list[SemanticDerivedResultPointerModel]:
        rows = list(
            self.session.scalars(
                select(SemanticDerivedResultPointerModel).where(
                    SemanticDerivedResultPointerModel.graph_set_id == graph_set_id,
                    SemanticDerivedResultPointerModel.status == "current",
                )
            )
        )
        now = datetime.now(UTC).isoformat()
        for row in rows:
            row.status = "stale"
            row.pointer_metadata = {
                **(row.pointer_metadata or {}),
                "stale_reason": reason,
                "stale_at": now,
                "stale_audit_id": audit_id,
            }
        self._mark_projection_manifests_stale(
            [graph_set_id], audit_id=audit_id, reason=reason, stale_at=now
        )
        if commit:
            self.session.commit()
        return rows

    def _mark_projection_manifests_stale(
        self,
        graph_set_ids: list[str],
        *,
        audit_id: str | None,
        reason: str,
        stale_at: str,
    ) -> None:
        manifests = self.session.scalars(
            select(SemanticProjectionManifestModel).where(
                SemanticProjectionManifestModel.graph_set_id.in_(graph_set_ids),
                SemanticProjectionManifestModel.status == "current",
            )
        )
        for manifest in manifests:
            manifest.status = "stale"
            manifest.manifest_metadata = {
                **(manifest.manifest_metadata or {}),
                "stale_reason": reason,
                "stale_at": stale_at,
                "stale_audit_id": audit_id,
            }


    def _graph_sets_containing(self, graph_iris: list[str]) -> list[str]:
        rows = self.session.scalars(
            select(SemanticGraphSetMemberModel.graph_set_id)
            .where(SemanticGraphSetMemberModel.graph_iri.in_(graph_iris))
            .distinct()
        )
        return list(rows)
