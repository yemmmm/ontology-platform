"""Projection job lifecycle: create, snapshot inputs, run, manifest promotion, reconcile.

Phase 6 graph-set-aware projection jobs. Each job snapshots the source
signature, input graph revisions, and input derived pointers; writers
implement the ``ProjectionWriter`` protocol. Successful rebuilds promote
a manifest for ``(graph_set_id, projection_kind, target_partition)`` to
``current``. Reconcile compares each manifest to the current graph-set
signature and derived-pointer statuses and marks stale when they diverge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetModel,
    SemanticProjectionJobModel,
    SemanticProjectionManifestModel,
)
from app.services.semantic_read_scope import (
    ScopeResolution,
    SemanticReadScopeResolver,
)


class ProjectionJobError(RuntimeError):
    status_code = 400


class ProjectionWriter(Protocol):
    kind: str

    def rebuild(
        self,
        job_id: str,
        scope: ScopeResolution,
        partition: str,
    ) -> dict[str, int]:
        ...


class SemanticProjectionJobService:
    def __init__(
        self,
        session: Session,
        writers: dict[str, ProjectionWriter],
        scope_resolver_builder: Callable[[Session], SemanticReadScopeResolver],
    ) -> None:
        self.session = session
        self.writers = writers
        self.scope_resolver_builder = scope_resolver_builder

    # ------------------------------------------------------------------ create
    def create_job(
        self,
        graph_set_id: str,
        projection_kind: str,
        projection_version: str,
        include: str = "asserted",
        mode: str = "rebuild",
        target_partition: str | None = None,
        allow_stale_derived: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticProjectionJobModel:
        graph_set = self._get_graph_set(graph_set_id)
        scope = self.scope_resolver_builder(self.session).resolve(
            graph_set_id=graph_set_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        revisions = self._revisions_for(scope.source_graph_iris)
        pointers = self._derived_pointers(graph_set_id)
        partition = target_partition or self._default_partition(
            graph_set_id, projection_kind, projection_version
        )
        job = SemanticProjectionJobModel(
            id=str(uuid4()),
            graph_set_id=graph_set_id,
            projection_kind=projection_kind,
            projection_version=projection_version,
            projection_scope=include,
            source_graph_iris=scope.source_graph_iris,
            reasoning_result_graph_iri=scope.reasoning_result_graph_iri,
            rule_result_graph_iri=scope.rule_result_graph_iri,
            source_signature=graph_set.source_signature,
            input_graph_revisions=revisions,
            input_derived_pointers=pointers,
            target_store=self._target_store_for(projection_kind),
            target_partition=partition,
            status="pending",
            started_at=None,
            finished_at=None,
            job_metadata={
                **(metadata or {}),
                "warnings": list(scope.warnings),
                "mode": mode,
            },
        )
        self.session.add(job)
        self.session.commit()
        return job

    # -------------------------------------------------------------------- run
    def run_job(self, job_id: str) -> SemanticProjectionJobModel:
        job = self._get_job(job_id)
        mode = (job.job_metadata or {}).get("mode", "rebuild")
        if mode == "reconcile":
            self._reconcile_one(job)
            return job
        job.status = "running"
        job.started_at = datetime.now(UTC)
        self.session.commit()
        try:
            scope = self.scope_resolver_builder(self.session).resolve(
                graph_set_id=job.graph_set_id,
                include=job.projection_scope,
                allow_stale_derived=True,
            )
            if mode != "dry_run":
                writer = self.writers.get(job.projection_kind)
                if writer is None:
                    raise ProjectionJobError(
                        f"No writer registered for kind: {job.projection_kind}"
                    )
                counts = writer.rebuild(
                    job_id=job.id,
                    scope=scope,
                    partition=job.target_partition or "",
                )
                job.node_count = int(counts.get("node_count", 0))
                job.relationship_count = int(counts.get("relationship_count", 0))
                job.document_count = int(counts.get("document_count", 0))
            job.status = "succeeded"
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            if mode == "rebuild":
                self._promote_manifest(job)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            raise
        return job

    # -------------------------------------------------------------- reconcile
    def reconcile(self) -> dict[str, Any]:
        marked: list[str] = []
        reconciled = 0
        rows = self.session.scalars(select(SemanticProjectionManifestModel))
        for manifest in rows:
            reconciled += 1
            graph_set = self._get_graph_set(manifest.graph_set_id)
            if manifest.source_signature != graph_set.source_signature:
                manifest.status = "stale"
                marked.append(manifest.id)
                continue
            pointers = self._derived_pointers(manifest.graph_set_id)
            for kind, payload in (
                manifest.manifest_metadata or {}
            ).get("input_derived_pointers", {}).items():
                current = pointers.get(kind, {})
                if payload.get("status") != current.get("status"):
                    manifest.status = "stale"
                    marked.append(manifest.id)
                    break
        self.session.commit()
        return {
            "reconciled": reconciled,
            "marked_stale": marked,
            "warnings": [],
        }

    # ------------------------------------------------------------------ status
    def status(self, graph_set_id: str | None = None) -> dict[str, Any]:
        statement = select(SemanticProjectionManifestModel)
        if graph_set_id:
            statement = statement.where(
                SemanticProjectionManifestModel.graph_set_id == graph_set_id
            )
        manifests = list(self.session.scalars(statement))
        stale: list[str] = []
        missing: list[str] = []
        for manifest in manifests:
            graph_set = self.session.get(SemanticGraphSetModel, manifest.graph_set_id)
            if graph_set is None:
                missing.append(manifest.id)
                continue
            if (
                manifest.status == "stale"
                or manifest.source_signature != graph_set.source_signature
            ):
                stale.append(manifest.id)
        return {
            "manifests": [self._manifest_dict(m) for m in manifests],
            "stale": stale,
            "stale_projection_count": len(stale),
            "missing": missing,
        }

    # ------------------------------------------------------------- list / get
    def list_jobs(
        self,
        graph_set_id: str | None = None,
        projection_kind: str | None = None,
        status: str | None = None,
    ) -> list[SemanticProjectionJobModel]:
        statement = select(SemanticProjectionJobModel).order_by(
            SemanticProjectionJobModel.started_at.desc().nullslast()
        )
        if graph_set_id:
            statement = statement.where(
                SemanticProjectionJobModel.graph_set_id == graph_set_id
            )
        if projection_kind:
            statement = statement.where(
                SemanticProjectionJobModel.projection_kind == projection_kind
            )
        if status:
            statement = statement.where(SemanticProjectionJobModel.status == status)
        return list(self.session.scalars(statement))

    def get_job(self, job_id: str) -> SemanticProjectionJobModel:
        return self._get_job(job_id)

    # ----------------------------------------------------------------- helpers
    def _get_graph_set(self, graph_set_id: str) -> SemanticGraphSetModel:
        record = self.session.get(SemanticGraphSetModel, graph_set_id)
        if record is None:
            raise ProjectionJobError(f"Graph set not found: {graph_set_id}")
        return record

    def _get_job(self, job_id: str) -> SemanticProjectionJobModel:
        record = self.session.get(SemanticProjectionJobModel, job_id)
        if record is None:
            raise ProjectionJobError(f"Projection job not found: {job_id}")
        return record

    def _revisions_for(self, graph_iris: list[str]) -> dict[str, int]:
        if not graph_iris:
            return {}
        rows = self.session.scalars(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri.in_(graph_iris)
            )
        )
        return {row.graph_iri: row.revision for row in rows}

    def _derived_pointers(self, graph_set_id: str) -> dict[str, dict[str, Any]]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.graph_set_id == graph_set_id
            )
        )
        return {
            row.result_kind: {
                "run_id": row.run_id,
                "result_graph_iri": row.result_graph_iri,
                "status": row.status,
            }
            for row in rows
        }

    def _promote_manifest(self, job: SemanticProjectionJobModel) -> None:
        manifest = self.session.scalar(
            select(SemanticProjectionManifestModel).where(
                SemanticProjectionManifestModel.graph_set_id == job.graph_set_id,
                SemanticProjectionManifestModel.projection_kind == job.projection_kind,
                SemanticProjectionManifestModel.target_partition
                == (job.target_partition or ""),
            )
        )
        payload = {
            "input_derived_pointers": job.input_derived_pointers or {},
            "node_count": job.node_count,
            "relationship_count": job.relationship_count,
            "document_count": job.document_count,
            "writer_version": "v1",
        }
        if manifest is None:
            manifest = SemanticProjectionManifestModel(
                id=str(uuid4()),
                graph_set_id=job.graph_set_id,
                projection_kind=job.projection_kind,
                active_job_id=job.id,
                source_signature=job.source_signature,
                projection_version=job.projection_version,
                target_partition=job.target_partition or "",
                status="current",
                manifest_metadata=payload,
            )
            self.session.add(manifest)
        else:
            manifest.active_job_id = job.id
            manifest.source_signature = job.source_signature
            manifest.projection_version = job.projection_version
            manifest.status = "current"
            manifest.manifest_metadata = payload
        self.session.commit()

    def _reconcile_one(self, job: SemanticProjectionJobModel) -> None:
        job.status = "running"
        job.started_at = job.started_at or datetime.now(UTC)
        self.session.commit()
        self.reconcile()
        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        self.session.commit()

    def _default_partition(
        self, graph_set_id: str, kind: str, version: str
    ) -> str:
        return f"{graph_set_id}/{kind}/{version}"

    def _target_store_for(self, kind: str) -> str | None:
        return {
            "search": "search",
            "vector": "vector",
            "business_json": "postgres_cache",
            "export_cache": "postgres_cache",
        }.get(kind)

    def _manifest_dict(
        self, manifest: SemanticProjectionManifestModel
    ) -> dict[str, Any]:
        return {
            "id": manifest.id,
            "graph_set_id": manifest.graph_set_id,
            "projection_kind": manifest.projection_kind,
            "active_job_id": manifest.active_job_id,
            "source_signature": manifest.source_signature,
            "projection_version": manifest.projection_version,
            "target_partition": manifest.target_partition,
            "status": manifest.status,
            "updated_at": manifest.updated_at,
            "metadata": manifest.manifest_metadata or {},
        }
