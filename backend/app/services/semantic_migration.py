"""Phase 7 canonical RDF dataset migration orchestrator.

Coordinates the preflight → dry-run → shadow backfill → dual-write compare →
RDF-primary cutover → legacy deprecation flow described in
``docs/architecture/semantic/phase7-canonical-rdf-dataset-migration.md``.

The service is environment-agnostic: it operates against any combination of
existing product tables and RDF-derived projections through a parity comparator
protocol, so the same orchestrator works in development (with seeded fixtures)
and in production (with full legacy tables).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticMigrationBatchModel,
    SemanticMigrationParityReportModel,
    SemanticMigrationRunModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_canonical_write import CanonicalSemanticWriteService
from app.services.semantic_command_compiler import (
    CompiledCommand,
    compile_command,
)
from app.services.semantic_graph_set import SemanticGraphSetService

logger = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    status_code = 400


class PreflightFailed(MigrationError):
    pass


class CutoverBlocked(MigrationError):
    status_code = 409


class RollbackBlocked(MigrationError):
    status_code = 409


class UnsupportedMigrationMode(MigrationError):
    pass


class MigrationRunNotFound(MigrationError):
    status_code = 404


# ---------------------------------------------------------------------------
# Source inventory & parity comparator protocols
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MigrationInventoryItem:
    """One row in the migration inventory.

    ``object_kind`` is the canonical Phase 7 kind ('class', 'property',
    'entity', 'relation', 'fact_claim', 'evidence', 'catalog_mapping', ...).
    ``source_id`` is the legacy id. ``payload`` is the data the compiler will
    turn into RDF.
    """

    object_kind: str
    source_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class MigrationInventory:
    items: list[MigrationInventoryItem]
    counts_by_kind: dict[str, int]
    unsupported: list[dict[str, Any]]
    source_signature: str
    warnings: list[str]

    @property
    def total(self) -> int:
        return len(self.items)


class SourceInventoryProvider(Protocol):
    """Builds a deterministic inventory for a given scope."""

    def __call__(
        self,
        session: Session,
        scope_type: str,
        scope_id: str | None,
    ) -> MigrationInventory: ...


class LegacyProjectionProvider(Protocol):
    """Returns the legacy-derived projection rows for one parity check."""

    def __call__(
        self,
        session: Session,
        scope_type: str,
        scope_id: str | None,
        check_name: str,
    ) -> list[dict[str, Any]]: ...


class ParityCheckRegistry:
    """Default registry of named parity checks.

    Each entry maps a stable check name to a callable that returns the RDF-side
    projection rows for that check. A separate ``legacy_provider`` returns the
    legacy rows. Comparison is by deep equality on JSON-normalized row sets.
    """

    def __init__(
        self,
        checks: dict[str, Callable[[Session, str, str | None], list[dict[str, Any]]]],
        legacy_provider: LegacyProjectionProvider | None = None,
    ) -> None:
        self._checks = checks
        self._legacy_provider = legacy_provider

    def check_names(self) -> list[str]:
        return sorted(self._checks)

    def run_check(
        self,
        session: Session,
        scope_type: str,
        scope_id: str | None,
        check_name: str,
    ) -> dict[str, Any]:
        check = self._checks.get(check_name)
        if check is None:
            return {
                "status": "skipped",
                "legacy_count": None,
                "rdf_count": None,
                "diff_summary": {"reason": "unknown_check"},
                "sample_diffs": [],
            }
        rdf_rows = list(check(session, scope_type, scope_id))
        if self._legacy_provider is None:
            legacy_rows: list[dict[str, Any]] = []
        else:
            legacy_rows = list(self._legacy_provider(session, scope_type, scope_id, check_name))
        legacy_normalized = _normalize_rows(legacy_rows)
        rdf_normalized = _normalize_rows(rdf_rows)
        legacy_only = [row for row in legacy_normalized if row not in rdf_normalized]
        rdf_only = [row for row in rdf_normalized if row not in legacy_normalized]
        status = "passed" if not legacy_only and not rdf_only else "failed"
        return {
            "status": status,
            "legacy_count": len(legacy_rows),
            "rdf_count": len(rdf_rows),
            "diff_summary": {
                "legacy_only": len(legacy_only),
                "rdf_only": len(rdf_only),
                "matched": len(legacy_normalized) - len(legacy_only),
            },
            "sample_diffs": [
                {"side": "legacy_only", "row": row}
                for row in legacy_only[:5]
            ] + [
                {"side": "rdf_only", "row": row}
                for row in rdf_only[:5]
            ],
        }


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort and JSON-canonicalize rows for order-insensitive comparison."""
    normalized = [
        json.loads(json.dumps(row, sort_keys=True, default=str)) for row in rows
    ]
    return sorted(normalized, key=lambda row: json.dumps(row, sort_keys=True))


# ---------------------------------------------------------------------------
# Migration service
# ---------------------------------------------------------------------------


class SemanticMigrationService:
    """Phase 7 migration orchestrator.

    Each public method maps to a step in the phase 7 flow:

    * :meth:`preflight`        — readiness checks; never writes RDF.
    * :meth:`create_run`       — record a dry-run / shadow / cutover / rollback run.
    * :meth:`plan_batches`     — deterministic batch plan from inventory.
    * :meth:`run_next_batch`   — execute the next pending batch (idempotent).
    * :meth:`rerun_failed_batches`
    * :meth:`run_parity_check` — run one or all parity checks for the scope.
    * :meth:`cutover`          — guarded switch to RDF primary read/write mode.
    * :meth:`rollback`         — restore legacy-primary mode for the scope.
    """

    DEFAULT_BATCH_SIZE = 200

    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        *,
        canonical_write_service: CanonicalSemanticWriteService | None = None,
        graph_set_service: SemanticGraphSetService | None = None,
        inventory_provider: SourceInventoryProvider | None = None,
        parity_registry: ParityCheckRegistry | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.canonical_write_service = canonical_write_service or CanonicalSemanticWriteService(
            session, rdf_store, settings
        )
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)
        self.inventory_provider = inventory_provider
        self.parity_registry = parity_registry or ParityCheckRegistry({})

    # ------------------------------------------------------------------
    # Inventory & preflight
    # ------------------------------------------------------------------

    def build_inventory(
        self,
        scope_type: str,
        scope_id: str | None,
    ) -> MigrationInventory:
        if self.inventory_provider is None:
            return _empty_inventory(scope_type, scope_id)
        return self.inventory_provider(self.session, scope_type, scope_id)

    def preflight(
        self,
        scope_type: str,
        scope_id: str | None,
        target_graph_set_id: str | None = None,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        warnings: list[str] = []

        ok, message = _check_oxigraph(self.rdf_store)
        checks.append({"name": "oxigraph_reachable", "status": "passed" if ok else "failed", "message": message})
        if not ok:
            warnings.append("Oxigraph is not reachable")

        checks.append(_preflight_check(
            "namespace_manifest_version",
            bool(self.settings.semantic_migration_phase2_mapping_version),
            f"phase2 mapping version={self.settings.semantic_migration_phase2_mapping_version}",
        ))

        inventory = self.build_inventory(scope_type, scope_id)
        checks.append(_preflight_check(
            "inventory_complete",
            not inventory.unsupported,
            f"inventory items={inventory.total}, unsupported={len(inventory.unsupported)}",
        ))
        if inventory.unsupported:
            warnings.append(
                f"Unsupported source records: {len(inventory.unsupported)}"
            )

        checks.append(_preflight_check(
            "parity_registry_size",
            True,
            f"parity checks={len(self.parity_registry.check_names())}",
        ))
        if not self.parity_registry.check_names():
            warnings.append("Parity registry is empty; cutover will skip mandatory checks")

        ready = all(check["status"] == "passed" for check in checks)
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "ready": ready,
            "checks": checks,
            "inventory": {
                "total": inventory.total,
                "counts_by_kind": inventory.counts_by_kind,
                "unsupported": inventory.unsupported,
                "source_signature": inventory.source_signature,
            },
            "warnings": warnings,
            "target_graph_set_id": target_graph_set_id,
        }

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def create_run(
        self,
        *,
        scope_type: str,
        scope_id: str | None,
        mode: str,
        target_graph_set_id: str | None = None,
        batch_size: int | None = None,
        created_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode not in {"dry_run", "shadow", "dual_write_backfill", "cutover", "rollback"}:
            raise UnsupportedMigrationMode(f"Unsupported migration mode: {mode}")
        if scope_type not in {
            "project", "ontology", "version", "catalog_source",
            "connector_source", "global", "ad_hoc",
        }:
            raise MigrationError(f"Unsupported scope_type: {scope_type}")

        inventory = self.build_inventory(scope_type, scope_id)
        run = SemanticMigrationRunModel(
            id=str(uuid4()),
            scope_type=scope_type,
            scope_id=scope_id,
            mode=mode,
            status="pending",
            phase2_mapping_version=self.settings.semantic_migration_phase2_mapping_version,
            source_snapshot_signature=inventory.source_signature,
            target_graph_set_id=target_graph_set_id,
            created_by=created_by,
            run_metadata={
                "batch_size": batch_size or self.settings.semantic_migration_batch_size,
                "requested_mode": mode,
                "target_graph_set_id": target_graph_set_id,
                **(metadata or {}),
            },
        )
        self.session.add(run)
        self._plan_batches(run, inventory, batch_size or self.settings.semantic_migration_batch_size)
        self.session.commit()
        return self._serialize_run(run)

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        return self._serialize_run(run)

    def list_runs(self, limit: int = 50) -> dict[str, Any]:
        rows = self.session.scalars(
            select(SemanticMigrationRunModel)
            .order_by(SemanticMigrationRunModel.started_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        items = [self._serialize_run(row, include_children=False) for row in rows]
        return {"items": items, "total": len(items)}

    def run_next_batch(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run.status == "rolled_back":
            return {
                "run_id": run.id,
                "status": run.status,
                "batch": None,
                "applied": False,
                "warnings": ["Run is rolled back"],
            }
        batch = self.session.scalar(
            select(SemanticMigrationBatchModel)
            .where(
                SemanticMigrationBatchModel.migration_run_id == run.id,
                SemanticMigrationBatchModel.status.in_(["pending", "failed"]),
            )
            .order_by(SemanticMigrationBatchModel.batch_index)
        )
        if batch is None:
            if run.status != "succeeded":
                run.status = "succeeded"
                run.finished_at = datetime.now(UTC)
                self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "batch": None,
                "applied": False,
                "warnings": ["No pending batches remain"],
            }
        run.status = "running"
        run.finished_at = None
        self.session.commit()
        try:
            applied = self._apply_batch(run, batch)
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            batch.status = "failed"
            batch.error = str(exc)
            batch.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "batch": self._serialize_batch(batch),
                "applied": False,
                "warnings": [str(exc)],
            }
        all_done = not bool(
            self.session.scalar(
                select(SemanticMigrationBatchModel)
                .where(
                    SemanticMigrationBatchModel.migration_run_id == run.id,
                    SemanticMigrationBatchModel.status.in_(["pending", "failed"]),
                )
                .limit(1)
            )
        )
        if all_done:
            run.status = "succeeded"
            run.finished_at = datetime.now(UTC)
        self.session.commit()
        return {
            "run_id": run.id,
            "status": run.status,
            "batch": self._serialize_batch(batch),
            "applied": applied,
            "warnings": [],
        }

    def rerun_failed_batches(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        rows = self.session.scalars(
            select(SemanticMigrationBatchModel)
            .where(
                SemanticMigrationBatchModel.migration_run_id == run.id,
                SemanticMigrationBatchModel.status == "failed",
            )
            .order_by(SemanticMigrationBatchModel.batch_index)
        )
        reset: list[str] = []
        for batch in rows:
            batch.status = "pending"
            batch.error = None
            batch.started_at = datetime.now(UTC)
            batch.finished_at = None
            reset.append(batch.id)
        if reset:
            run.status = "running"
            run.error = None
            run.finished_at = None
        self.session.commit()
        return {
            "run_id": run.id,
            "status": run.status,
            "reset_batches": reset,
            "warnings": [],
        }

    # ------------------------------------------------------------------
    # Parity & cutover
    # ------------------------------------------------------------------

    def run_parity_check(
        self,
        run_id: str,
        check_name: str | None = None,
    ) -> dict[str, Any]:
        run = self._require_run(run_id)
        names = (
            [check_name]
            if check_name
            else self.parity_registry.check_names()
        )
        reports: list[SemanticMigrationParityReportModel] = []
        blocking_failures: list[str] = []
        warnings: list[str] = []
        for name in names:
            result = self.parity_registry.run_check(
                self.session, run.scope_type, run.scope_id, name
            )
            report = SemanticMigrationParityReportModel(
                id=str(uuid4()),
                migration_run_id=run.id,
                check_name=name,
                scope_type=run.scope_type,
                scope_id=run.scope_id,
                status=result["status"],
                legacy_count=result["legacy_count"],
                rdf_count=result["rdf_count"],
                diff_summary=result["diff_summary"],
                sample_diffs=result["sample_diffs"],
                parity_metadata={"phase2_mapping_version": run.phase2_mapping_version},
            )
            self.session.add(report)
            reports.append(report)
            if result["status"] == "failed":
                blocking_failures.append(name)
            if result["status"] == "warned":
                warnings.append(f"{name} reported warnings")
        self.session.commit()
        mandatory_passed = not blocking_failures
        return {
            "run_id": run.id,
            "status": "passed" if mandatory_passed else "failed",
            "reports": [self._serialize_parity(report) for report in reports],
            "mandatory_passed": mandatory_passed,
            "blocking_failures": blocking_failures,
            "warnings": warnings,
        }

    def cutover(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run.mode != "cutover":
            raise CutoverBlocked(
                f"Cutover can only be triggered on a 'cutover' run; got mode={run.mode}"
            )
        if run.status not in {"pending", "running"}:
            raise CutoverBlocked(f"Run is in terminal state: {run.status}")

        parity = self.run_parity_check(run_id)
        if self.settings.semantic_migration_parity_required and not parity["mandatory_passed"]:
            raise CutoverBlocked(
                "Mandatory parity checks failed: " + ", ".join(parity["blocking_failures"])
            )
        previous_modes = {
            "canonical_store": self.settings.semantic_canonical_store,
            "product_write_mode": self.settings.semantic_product_write_mode,
            "read_mode": self.settings.semantic_read_mode,
            "legacy_write_blocked": self.settings.semantic_legacy_write_blocked,
        }
        new_modes = {
            "canonical_store": "rdf",
            "product_write_mode": "rdf_primary",
            "read_mode": "rdf",
            "legacy_write_blocked": True,
        }
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        run.run_metadata = {
            **(run.run_metadata or {}),
            "cutover": {
                "previous_modes": previous_modes,
                "new_modes": new_modes,
                "cut_over_at": datetime.now(UTC).isoformat(),
            },
        }
        self.session.commit()
        return {
            "run_id": run.id,
            "status": run.status,
            "previous_modes": previous_modes,
            "new_modes": new_modes,
            "gates_passed": True,
            "blocking_failures": [],
            "warnings": parity["warnings"],
        }

    def rollback(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run.status == "rolled_back":
            raise RollbackBlocked("Run is already rolled back")
        if run.mode == "rollback":
            run.status = "rolled_back"
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            return self._rollback_response(run, restored=True)
        if run.mode != "cutover":
            raise RollbackBlocked(
                f"Rollback is only valid for 'cutover' or 'rollback' runs; got mode={run.mode}"
            )
        run.status = "rolled_back"
        run.finished_at = datetime.now(UTC)
        run.run_metadata = {
            **(run.run_metadata or {}),
            "rollback": {
                "rolled_back_at": datetime.now(UTC).isoformat(),
                "restored_modes": {
                    "canonical_store": "legacy",
                    "product_write_mode": "legacy_only",
                    "read_mode": "legacy",
                    "legacy_write_blocked": False,
                },
            },
        }
        rolled_back_graphs: list[str] = []
        if run.target_graph_set_id:
            rolled_back_graphs = self._graph_set_graph_iris(run.target_graph_set_id)
        self.session.commit()
        return self._rollback_response(run, restored=True, rolled_back_graphs=rolled_back_graphs)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_run(self, run_id: str) -> SemanticMigrationRunModel:
        run = self.session.get(SemanticMigrationRunModel, run_id)
        if run is None:
            raise MigrationRunNotFound(f"Migration run not found: {run_id}")
        return run

    def _plan_batches(
        self,
        run: SemanticMigrationRunModel,
        inventory: MigrationInventory,
        batch_size: int,
    ) -> None:
        items_by_kind: dict[str, list[MigrationInventoryItem]] = {}
        for item in inventory.items:
            items_by_kind.setdefault(item.object_kind, []).append(item)
        batch_size = max(1, batch_size)
        index = 0
        for object_kind in sorted(items_by_kind):
            bucket = sorted(items_by_kind[object_kind], key=lambda item: item.source_id)
            for chunk_start in range(0, len(bucket), batch_size):
                chunk = bucket[chunk_start:chunk_start + batch_size]
                source_ids = [item.source_id for item in chunk]
                source_hash = _source_hash(chunk)
                # Stash object_kind into each payload so dry-run target-graph
                # inference can derive the same graph IRIs the writer will touch
                # without having to re-derive the kind from the source_id.
                annotated_payloads = [
                    {**item.payload, "object_kind": item.object_kind, "source_id": item.source_id}
                    for item in chunk
                ]
                batch = SemanticMigrationBatchModel(
                    id=str(uuid4()),
                    migration_run_id=run.id,
                    batch_index=index,
                    object_kind=object_kind,
                    source_ids=source_ids,
                    target_graph_iris=[],
                    status="pending",
                    source_hash=source_hash,
                    batch_metadata={
                        "payloads": annotated_payloads,
                        "phase2_mapping_version": run.phase2_mapping_version,
                    },
                )
                self.session.add(batch)
                index += 1

    def _apply_batch(
        self,
        run: SemanticMigrationRunModel,
        batch: SemanticMigrationBatchModel,
    ) -> bool:
        batch.status = "running"
        batch.started_at = datetime.now(UTC)
        self.session.commit()
        if run.mode == "dry_run":
            target_hash = _target_hash_for_payloads(
                batch.batch_metadata.get("payloads") or [],
                self.settings.semantic_migration_phase2_mapping_version,
            )
            batch.target_hash = target_hash
            batch.target_graph_iris = _expected_target_graph_iris(
                self.settings, batch.batch_metadata.get("payloads") or []
            )
            batch.status = "succeeded"
            batch.finished_at = datetime.now(UTC)
            batch.inserted_quad_count = 0
            batch.deleted_quad_count = 0
            return False
        if run.mode == "rollback":
            batch.status = "succeeded"
            batch.finished_at = datetime.now(UTC)
            return False
        # shadow / dual_write_backfill / cutover modes share the same write path
        payloads = batch.batch_metadata.get("payloads") or []
        target_hash = _target_hash_for_payloads(
            payloads, self.settings.semantic_migration_phase2_mapping_version
        )
        if batch.target_hash == target_hash and batch.status == "succeeded":
            batch.status = "succeeded"
            batch.finished_at = datetime.now(UTC)
            return False

        affected_graphs: set[str] = set()
        inserted = 0
        for payload in payloads:
            object_kind = payload.get("object_kind")
            command_kind = payload.get("command_kind")
            if not command_kind:
                if object_kind == "class":
                    command_kind = "create_class"
                elif object_kind == "relation_type":
                    command_kind = "create_relation_type"
                elif object_kind == "fact_claim":
                    logger.warning(
                        "Skipping legacy fact_claim migration row (id=%s): the "
                        "submit_assertion command and op:FactClaim model have been "
                        "removed. Re-bind evidence via the new fact_evidence_bindings "
                        "API after migration.",
                        payload.get("id") or payload.get("fact_claim_id"),
                    )
                    continue
                else:
                    continue
            if command_kind in {"submit_assertion", "update_evidence_status",
                                "bind_fact_evidence_text"}:
                logger.warning(
                    "Skipping legacy migration row (command_kind=%s, id=%s): "
                    "command removed in Phase 4 cleanup.",
                    command_kind,
                    payload.get("id") or payload.get("fact_claim_id"),
                )
                continue
            compiled: CompiledCommand = compile_command(command_kind, payload, self.settings)
            result = self.canonical_write_service.apply_compiled_command(
                compiled,
                graph_set_id=run.target_graph_set_id,
                actor=run.created_by,
                reason=f"migration run {run.id} batch {batch.batch_index}",
                validate=False,
            )
            affected_graphs.update(result["affected_graph_iris"])
            inserted += result["delta"]["inserted_quad_count"]
        batch.target_hash = target_hash
        batch.target_graph_iris = sorted(affected_graphs)
        batch.inserted_quad_count = inserted
        batch.deleted_quad_count = 0
        batch.status = "succeeded"
        batch.finished_at = datetime.now(UTC)
        return True

    def _graph_set_graph_iris(self, graph_set_id: str) -> list[str]:
        try:
            description = self.graph_set_service.describe(graph_set_id)
        except Exception:
            return []
        return [member["graph_iri"] for member in description.get("members", [])]

    def _serialize_run(
        self,
        run: SemanticMigrationRunModel,
        include_children: bool = True,
    ) -> dict[str, Any]:
        data = {
            "id": run.id,
            "scope_type": run.scope_type,
            "scope_id": run.scope_id,
            "mode": run.mode,
            "status": run.status,
            "phase2_mapping_version": run.phase2_mapping_version,
            "source_snapshot_signature": run.source_snapshot_signature,
            "target_graph_set_id": run.target_graph_set_id,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "created_by": run.created_by,
            "error": run.error,
            "metadata": run.run_metadata or {},
        }
        if not include_children:
            return data
        data["batches"] = [self._serialize_batch(b) for b in run.batches]
        data["parity_reports"] = [
            self._serialize_parity(p) for p in run.parity_reports
        ]
        return data

    def _serialize_batch(self, batch: SemanticMigrationBatchModel) -> dict[str, Any]:
        return {
            "id": batch.id,
            "migration_run_id": batch.migration_run_id,
            "batch_index": batch.batch_index,
            "object_kind": batch.object_kind,
            "source_ids": batch.source_ids,
            "target_graph_iris": batch.target_graph_iris,
            "status": batch.status,
            "inserted_quad_count": batch.inserted_quad_count,
            "deleted_quad_count": batch.deleted_quad_count,
            "source_hash": batch.source_hash,
            "target_hash": batch.target_hash,
            "started_at": batch.started_at,
            "finished_at": batch.finished_at,
            "error": batch.error,
            "metadata": batch.batch_metadata or {},
        }

    def _serialize_parity(self, report: SemanticMigrationParityReportModel) -> dict[str, Any]:
        return {
            "id": report.id,
            "migration_run_id": report.migration_run_id,
            "check_name": report.check_name,
            "scope_type": report.scope_type,
            "scope_id": report.scope_id,
            "status": report.status,
            "legacy_count": report.legacy_count,
            "rdf_count": report.rdf_count,
            "diff_summary": report.diff_summary,
            "sample_diffs": report.sample_diffs,
            "created_at": report.created_at,
            "metadata": report.parity_metadata or {},
        }

    def _rollback_response(
        self,
        run: SemanticMigrationRunModel,
        *,
        restored: bool,
        rolled_back_graphs: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "status": run.status,
            "restored_modes": {
                "canonical_store": "legacy",
                "product_write_mode": "legacy_only",
                "read_mode": "legacy",
                "legacy_write_blocked": False,
            },
            "rolled_back_graphs": rolled_back_graphs or [],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _preflight_check(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "message": message,
    }


def _check_oxigraph(rdf_store: RdfStoreRepository) -> tuple[bool, str]:
    try:
        rdf_store.health()
    except Exception as exc:
        return False, f"oxigraph health failed: {exc}"
    return True, "ok"


def _empty_inventory(scope_type: str, scope_id: str | None) -> MigrationInventory:
    signature = hashlib.sha256(
        f"{scope_type}:{scope_id or ''}".encode("utf-8")
    ).hexdigest()
    return MigrationInventory(
        items=[],
        counts_by_kind={},
        unsupported=[],
        source_signature=signature[:32],
        warnings=["No inventory provider configured"],
    )


def _source_hash(items: list[MigrationInventoryItem]) -> str:
    payload = json.dumps(
        [
            {"object_kind": item.object_kind, "source_id": item.source_id, "payload": item.payload}
            for item in items
        ],
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _target_hash_for_payloads(payloads: list[dict[str, Any]], mapping_version: str) -> str:
    payload = json.dumps(
        {"payloads": payloads, "mapping_version": mapping_version},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expected_target_graph_iris(
    settings: Settings,
    payloads: list[dict[str, Any]],
) -> list[str]:
    """Compute deterministic expected target graph IRIs for dry-run plans."""
    prefix = settings.semantic_graph_iri_prefix.rstrip("/")
    iris: set[str] = set()
    for payload in payloads:
        ontology_id = payload.get("ontology_id")
        if not ontology_id:
            continue
        if payload.get("object_kind") in {"class", "relation_type", "property"}:
            iris.add(f"{prefix}/ontology/{ontology_id}")
        else:
            iris.add(f"{prefix}/data/{ontology_id}")
    return sorted(iris)


__all__ = [
    "CutoverBlocked",
    "MigrationError",
    "MigrationInventory",
    "MigrationInventoryItem",
    "MigrationRunNotFound",
    "ParityCheckRegistry",
    "PreflightFailed",
    "RollbackBlocked",
    "SemanticMigrationService",
    "SourceInventoryProvider",
    "UnsupportedMigrationMode",
]
