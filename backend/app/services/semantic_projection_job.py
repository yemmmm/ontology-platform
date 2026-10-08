"""Projection job lifecycle: create, snapshot inputs, run, manifest promotion, reconcile.

Each job binds one Ontology model revision. A successful rebuild promotes its
partition only while that revision remains current. Historical pointer slots
are retained for stored evidence; they cannot become live projection inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import (
    OntologyModel,
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
        ontology_id: str,
        projection_kind: str,
        projection_version: str,
        include: str = "asserted",
        mode: str = "rebuild",
        target_partition: str | None = None,
        allow_stale_derived: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticProjectionJobModel:
        ontology = self._get_ontology(ontology_id)
        scope = self.scope_resolver_builder(self.session).resolve(
            ontology_id=ontology_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        pointers = {}
        job_id = str(uuid4())
        partition = target_partition or self._default_partition(
            ontology_id, projection_kind, projection_version, job_id
        )
        job = SemanticProjectionJobModel(
            id=job_id,
            ontology_id=ontology_id,
            projection_kind=projection_kind,
            projection_version=projection_version,
            projection_scope=include,
            model_graph_iris=scope.model_graph_iris,
            reasoning_result_graph_iri=scope.reasoning_result_graph_iri,
            model_revision=ontology.model_revision,
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
                ontology_id=job.ontology_id,
                include=job.projection_scope,
                allow_stale_derived=True,
            )
            if scope.model_revision != job.model_revision:
                job.status = "stale"
                job.finished_at = datetime.now(UTC)
                self.session.commit()
                return job
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
            # A writer is allowed to take time (notably while embedding).  Do
            # not promote a partition that was built from a superseded scope.
            self.session.flush()
            self.session.expire_all()
            job = self._get_job(job_id)
            current_ontology = self._get_ontology(job.ontology_id)
            if (
                current_ontology.model_revision != job.model_revision
                or {} != (job.input_derived_pointers or {})
            ):
                job.status = "stale"
                job.finished_at = datetime.now(UTC)
                self.session.commit()
                return job
            job.status = "succeeded"
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            if mode == "rebuild":
                self._promote_manifest(job)
        except Exception as exc:
            # A writer can fail during ``flush`` (for example an immutable
            # retrieval partition colliding with a prior build).  SQLAlchemy
            # then marks this session inactive, so the failure lifecycle must
            # start with a rollback and reload before it can be persisted.
            self.session.rollback()
            failed_job = self._get_job(job_id)
            failed_job.status = "failed"
            failed_job.error = str(exc)
            failed_job.finished_at = datetime.now(UTC)
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
            ontology = self._get_ontology(manifest.ontology_id)
            if manifest.model_revision != ontology.model_revision:
                manifest.status = "stale"
                marked.append(manifest.id)
                continue
            if (manifest.manifest_metadata or {}).get("input_derived_pointers"):
                manifest.status = "stale"
                marked.append(manifest.id)
        self.session.commit()
        return {
            "reconciled": reconciled,
            "marked_stale": marked,
            "warnings": [],
        }

    # ------------------------------------------------------------------ status
    def status(self, ontology_id: str | None = None) -> dict[str, Any]:
        statement = select(SemanticProjectionManifestModel)
        if ontology_id:
            statement = statement.where(
                SemanticProjectionManifestModel.ontology_id == ontology_id
            )
        manifests = list(self.session.scalars(statement))
        stale: list[str] = []
        missing: list[str] = []
        for manifest in manifests:
            ontology = self.session.get(OntologyModel, manifest.ontology_id)
            if ontology is None:
                missing.append(manifest.id)
                continue
            if (
                manifest.status == "stale"
                or manifest.model_revision != ontology.model_revision
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
        ontology_id: str | None = None,
        projection_kind: str | None = None,
        status: str | None = None,
    ) -> list[SemanticProjectionJobModel]:
        statement = select(SemanticProjectionJobModel).order_by(
            SemanticProjectionJobModel.started_at.desc().nullslast()
        )
        if ontology_id:
            statement = statement.where(
                SemanticProjectionJobModel.ontology_id == ontology_id
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
    def _get_ontology(self, ontology_id: str) -> OntologyModel:
        record = self.session.get(OntologyModel, ontology_id)
        if record is None:
            raise ProjectionJobError(f"Ontology not found: {ontology_id}")
        return record

    def _get_job(self, job_id: str) -> SemanticProjectionJobModel:
        record = self.session.get(SemanticProjectionJobModel, job_id)
        if record is None:
            raise ProjectionJobError(f"Projection job not found: {job_id}")
        return record

    def _promote_manifest(self, job: SemanticProjectionJobModel) -> None:
        ontology = self.session.scalar(
            select(OntologyModel).where(OntologyModel.id == job.ontology_id)
            .with_for_update().execution_options(populate_existing=True)
        )
        if ontology.model_revision != job.model_revision:
            job.status = "stale"
            self.session.commit()
            return
        # A projection partition becomes queryable only when it is the one
        # current partition for this Ontology/kind.  Older partitions remain
        # recoverable but cannot leak into a current query.
        for prior in self.session.scalars(
            select(SemanticProjectionManifestModel).where(
                SemanticProjectionManifestModel.ontology_id == job.ontology_id,
                SemanticProjectionManifestModel.projection_kind == job.projection_kind,
                SemanticProjectionManifestModel.status == "current",
            )
        ):
            prior.status = "stale"
        manifest = self.session.scalar(
            select(SemanticProjectionManifestModel).where(
                SemanticProjectionManifestModel.ontology_id == job.ontology_id,
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
                ontology_id=job.ontology_id,
                projection_kind=job.projection_kind,
                active_job_id=job.id,
                model_revision=job.model_revision,
                projection_version=job.projection_version,
                target_partition=job.target_partition or "",
                status="current",
                manifest_metadata=payload,
            )
            self.session.add(manifest)
        else:
            manifest.active_job_id = job.id
            manifest.model_revision = job.model_revision
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
        self, ontology_id: str, kind: str, version: str, job_id: str
    ) -> str:
        return f"{ontology_id}/{kind}/{version}/{job_id}"

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
            "ontology_id": manifest.ontology_id,
            "projection_kind": manifest.projection_kind,
            "active_job_id": manifest.active_job_id,
            "model_revision": manifest.model_revision,
            "projection_version": manifest.projection_version,
            "target_partition": manifest.target_partition,
            "status": manifest.status,
            "updated_at": manifest.updated_at,
            "metadata": manifest.manifest_metadata or {},
        }
