"""Source-graph revisions, derived-result pointers, and staleness reconciliation."""

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
from app.services.semantic_graph_set import SemanticGraphSetService


class DerivedStateError(RuntimeError):
    status_code = 400


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

    def promote_reasoning_pointer(
        self,
        graph_set_id: str,
        run_id: str,
        result_graph_iri: str,
        source_signature: str,
        engine_name: str | None = None,
        engine_version: str | None = None,
        shape_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticDerivedResultPointerModel:
        return self._promote(
            graph_set_id=graph_set_id,
            result_kind="reasoning",
            run_id=run_id,
            result_graph_iri=result_graph_iri,
            source_signature=source_signature,
            engine_name=engine_name,
            engine_version=engine_version,
            shape_version=shape_version,
            metadata=metadata,
        )

    def promote_rule_pointer(
        self,
        graph_set_id: str,
        run_id: str,
        result_graph_iri: str,
        source_signature: str,
        engine_name: str | None = None,
        engine_version: str | None = None,
        rule_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticDerivedResultPointerModel:
        return self._promote(
            graph_set_id=graph_set_id,
            result_kind="rule",
            run_id=run_id,
            result_graph_iri=result_graph_iri,
            source_signature=source_signature,
            engine_name=engine_name,
            engine_version=engine_version,
            rule_version=rule_version,
            metadata=metadata,
        )

    def mark_stale_after_edit(
        self,
        affected_graph_iris: list[str],
        audit_id: str | None = None,
    ) -> list[SemanticDerivedResultPointerModel]:
        if not affected_graph_iris:
            return []
        graph_set_ids = self._graph_sets_containing(affected_graph_iris)
        if not graph_set_ids:
            return []
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel)
            .where(
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
        if stale:
            self.session.commit()
        return stale

    def reconcile(self) -> dict[str, Any]:
        """Recompute stale/current/superseded state from signatures and revisions."""
        graph_sets = list(
            self.session.scalars(select(SemanticGraphSetModel).where(SemanticGraphSetModel.status == "active"))
        )
        reconciled_current = 0
        reconciled_stale = 0
        for graph_set in graph_sets:
            current_signature = SemanticGraphSetService(
                self.session, self.settings
            ).source_signature_for(graph_set.id)
            pointers = self.session.scalars(
                select(SemanticDerivedResultPointerModel)
                .where(SemanticDerivedResultPointerModel.graph_set_id == graph_set.id)
                .where(SemanticDerivedResultPointerModel.status != "superseded")
            )
            for pointer in pointers:
                if pointer.source_signature and pointer.source_signature != current_signature:
                    if pointer.status != "stale":
                        pointer.status = "stale"
                        pointer.pointer_metadata = {
                            **(pointer.pointer_metadata or {}),
                            "stale_reason": "source_signature_mismatch",
                        }
                        reconciled_stale += 1
                else:
                    if pointer.status == "stale" and not pointer.source_signature:
                        pointer.status = "current"
                        pointer.became_current_at = datetime.now(UTC)
                        reconciled_current += 1
        self.session.commit()
        return {
            "graph_sets_inspected": len(graph_sets),
            "pointers_marked_current": reconciled_current,
            "pointers_marked_stale": reconciled_stale,
        }

    def current_pointer(
        self,
        graph_set_id: str,
        result_kind: str,
    ) -> SemanticDerivedResultPointerModel | None:
        return self.session.scalar(
            select(SemanticDerivedResultPointerModel)
            .where(SemanticDerivedResultPointerModel.graph_set_id == graph_set_id)
            .where(SemanticDerivedResultPointerModel.result_kind == result_kind)
            .where(SemanticDerivedResultPointerModel.status == "current")
        )

    def list_pointers(
        self,
        graph_set_id: str | None = None,
        result_kind: str | None = None,
        status: str | None = None,
    ) -> list[SemanticDerivedResultPointerModel]:
        statement = select(SemanticDerivedResultPointerModel).order_by(
            SemanticDerivedResultPointerModel.created_at.desc()
        )
        if graph_set_id:
            statement = statement.where(
                SemanticDerivedResultPointerModel.graph_set_id == graph_set_id
            )
        if result_kind:
            statement = statement.where(
                SemanticDerivedResultPointerModel.result_kind == result_kind
            )
        if status:
            statement = statement.where(SemanticDerivedResultPointerModel.status == status)
        return list(self.session.scalars(statement))

    def status_summary(self) -> dict[str, Any]:
        rows = self.list_pointers()
        by_kind_status: dict[str, dict[str, int]] = {}
        for row in rows:
            kind_bucket = by_kind_status.setdefault(row.result_kind, {})
            kind_bucket[row.status] = kind_bucket.get(row.status, 0) + 1
        return {
            "derived_pointer_counts": by_kind_status,
            "stale_reasoning_results": by_kind_status.get("reasoning", {}).get("stale", 0),
            "stale_rule_results": by_kind_status.get("rule", {}).get("stale", 0),
            "current_reasoning_results": by_kind_status.get("reasoning", {}).get("current", 0),
            "current_rule_results": by_kind_status.get("rule", {}).get("current", 0),
        }

    def _promote(
        self,
        graph_set_id: str,
        result_kind: str,
        run_id: str,
        result_graph_iri: str,
        source_signature: str,
        engine_name: str | None,
        engine_version: str | None,
        rule_version: str | None = None,
        shape_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticDerivedResultPointerModel:
        prior_current = self.session.scalars(
            select(SemanticDerivedResultPointerModel)
            .where(SemanticDerivedResultPointerModel.graph_set_id == graph_set_id)
            .where(SemanticDerivedResultPointerModel.result_kind == result_kind)
            .where(SemanticDerivedResultPointerModel.status == "current")
        )
        now = datetime.now(UTC)
        for pointer in prior_current:
            pointer.status = "superseded"
            pointer.pointer_metadata = {
                **(pointer.pointer_metadata or {}),
                "superseded_at": now.isoformat(),
                "superseded_by_run": run_id,
            }
        pointer = SemanticDerivedResultPointerModel(
            id=str(uuid4()),
            graph_set_id=graph_set_id,
            result_kind=result_kind,
            run_id=run_id,
            result_graph_iri=result_graph_iri,
            source_signature=source_signature,
            engine_name=engine_name,
            engine_version=engine_version,
            rule_version=rule_version,
            shape_version=shape_version,
            status="current",
            became_current_at=now,
            pointer_metadata=metadata or {},
        )
        self.session.add(pointer)
        self.session.commit()
        return pointer

    def _graph_sets_containing(self, graph_iris: list[str]) -> list[str]:
        rows = self.session.scalars(
            select(SemanticGraphSetMemberModel.graph_set_id)
            .where(SemanticGraphSetMemberModel.graph_iri.in_(graph_iris))
            .distinct()
        )
        return list(rows)
