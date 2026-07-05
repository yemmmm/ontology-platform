"""Garbage collection for superseded reasoning-result graphs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphGcRunModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_graph_registry import (
    DERIVED_RESULT_CATEGORIES,
    GraphCategory,
)


class GraphGcError(RuntimeError):
    status_code = 400


class SemanticGraphGcService:
    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        retention_days: int = 7,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.retention_days = retention_days
        self.prefix = settings.semantic_graph_iri_prefix

    def list_candidates(
        self,
        target_kind: str = "reasoning_result",
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if target_kind != "reasoning_result":
            raise GraphGcError("Phase 4 GC only supports reasoning_result")
        rows = self._superseded_pointers(now or datetime.now(UTC))
        return [
            {
                "graph_iri": row.result_graph_iri,
                "result_kind": row.result_kind,
                "run_id": row.run_id,
                "graph_set_id": row.graph_set_id,
                "became_current_at": row.became_current_at,
                "superseded_metadata": row.pointer_metadata,
            }
            for row in rows
        ]

    def execute(
        self,
        target_kind: str = "reasoning_result",
        dry_run: bool = False,
        now: datetime | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        if target_kind != "reasoning_result":
            raise GraphGcError("Phase 4 GC only supports reasoning_result")
        candidates = self.list_candidates(target_kind, now=now)
        run = SemanticGraphGcRunModel(
            id=str(uuid4()),
            target_kind=target_kind,
            status="running",
            candidate_count=len(candidates),
            deleted_count=0,
            gc_metadata={"dry_run": dry_run, "retention_days": self.retention_days},
        )
        self.session.add(run)
        self.session.flush()
        deleted_graph_iris: list[str] = []
        errors: list[dict[str, Any]] = []
        for candidate in candidates:
            graph_iri = candidate["graph_iri"]
            if self._is_protected(graph_iri):
                errors.append(
                    {
                        "graph_iri": graph_iri,
                        "error": "Refused to delete protected graph category",
                    }
                )
                continue
            if dry_run:
                deleted_graph_iris.append(graph_iri)
                continue
            try:
                self.rdf_store.clear_graph(graph_iri)
                deleted_graph_iris.append(graph_iri)
            except Exception as exc:
                errors.append({"graph_iri": graph_iri, "error": str(exc)})
        run.deleted_count = len(deleted_graph_iris)
        run.gc_metadata = {
            **run.gc_metadata,
            "deleted_graph_iris": deleted_graph_iris,
            "errors": errors,
            "actor": actor,
        }
        run.status = "failed" if errors and not dry_run else "succeeded"
        run.finished_at = datetime.now(UTC)
        self.session.commit()
        return {
            "gc_run_id": run.id,
            "target_kind": run.target_kind,
            "status": run.status,
            "candidate_count": run.candidate_count,
            "deleted_count": run.deleted_count,
            "dry_run": dry_run,
            "deleted_graph_iris": deleted_graph_iris,
            "errors": errors,
        }

    def list_recent_runs(self, limit: int = 50) -> list[SemanticGraphGcRunModel]:
        bounded_limit = max(1, min(limit, 200))
        return list(
            self.session.scalars(
                select(SemanticGraphGcRunModel)
                .order_by(SemanticGraphGcRunModel.started_at.desc())
                .limit(bounded_limit)
            )
        )

    def _superseded_pointers(self, now: datetime) -> list[SemanticDerivedResultPointerModel]:
        cutoff = now.timestamp()
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel)
            .where(SemanticDerivedResultPointerModel.status == "superseded")
            .where(SemanticDerivedResultPointerModel.result_kind == "reasoning")
            .order_by(SemanticDerivedResultPointerModel.became_current_at.asc())
        )
        eligible: list[SemanticDerivedResultPointerModel] = []
        retention_seconds = self.retention_days * 86400
        for row in rows:
            if not row.result_graph_iri:
                continue
            if not row.result_graph_iri.startswith(self.prefix):
                continue
            superseded_at_value = (row.pointer_metadata or {}).get("superseded_at")
            if superseded_at_value:
                try:
                    parsed = datetime.fromisoformat(superseded_at_value).timestamp()
                    if cutoff - parsed < retention_seconds:
                        continue
                except ValueError:
                    pass
            eligible.append(row)
        return eligible

    def _is_protected(self, graph_iri: str) -> bool:
        if not graph_iri.startswith(self.prefix):
            return True
        suffix = graph_iri[len(self.prefix):]
        head = suffix.split("/", 1)[0].replace("-", "_").lower()
        try:
            category = GraphCategory(head)
        except ValueError:
            return True
        # Only derived-result categories are eligible; everything else protected.
        return category not in DERIVED_RESULT_CATEGORIES
