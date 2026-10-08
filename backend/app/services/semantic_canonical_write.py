"""Phase 7 canonical semantic write service.

After Phase 7 cutover, both direct semantic edits and structured product command
compilers route through this service so that:

  * graph deltas pass the necessary platform contract checks once,
  * editability is enforced before mutation,
  * audit metadata is recorded in one place,
  * graph revisions bump on every committed change,
  * derived result pointers and projection manifests get marked stale together.

Pre-cutover, callers may still use the Phase 1 ``SemanticService.apply_edit`` API
or the legacy product endpoints; this service is opt-in via the
``SEMANTIC_PRODUCT_WRITE_MODE`` setting.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    OntologyWriteFenceModel,
    SemanticEditAuditModel,
    SemanticGraphStateModel,
)
from app.repositories.rdf_store import (
    GraphWriteResult,
    RdfGraphDelta,
    RdfStoreRepository,
)
from app.services.semantic_command_compiler import (
    CompiledCommand,
    compile_command,
)
from app.services.semantic_derived_state import (
    SemanticDerivedStateService,
    SemanticRevisionService,
)
from app.services.semantic_graph_registry import (
    DirectEditCategoryDenied,
    GraphRegistryError,
    SemanticGraphRegistryService,
)
from app.services.semantic_lineage_recorder import SemanticLineageRecorder
from app.services.operation_semantics import OperationValidationError, validate_operation_delta
from app.services.semantic_retrieval import SemanticRetrievalCoordinator


class CanonicalSemanticWriteError(RuntimeError):
    status_code = 400


class CanonicalWriteBlocked(CanonicalSemanticWriteError):
    """Raised when the canonical writer is disabled for the current mode."""

    status_code = 409


class LockedCanonicalGraph(CanonicalSemanticWriteError):
    status_code = 409


class CanonicalValidationError(CanonicalSemanticWriteError):
    status_code = 422

    def __init__(self, message: str, validation_result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.validation_result = validation_result or {}




def _delta_to_dict(delta: RdfGraphDelta) -> dict[str, Any]:
    return {
        "operation": "insert_delete",
        "graph_iris": delta.affected_graph_iris(),
        "inserted_statements": [
            f"{subject} {predicate} {obj}" for subject, predicate, obj, _graph_iri in delta.inserts
        ],
        "removed_statements": [
            f"{subject} {predicate} {obj}" for subject, predicate, obj, _graph_iri in delta.deletes
        ],
        "inserted_quad_count": len(delta.inserts),
        "removed_quad_count": len(delta.deletes),
        "cleared_graphs": list(delta.clear_graphs),
        "dropped_graphs": list(delta.drop_graphs),
    }


class CanonicalSemanticWriteService:
    """Phase 7 shared write path."""

    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        graph_registry: SemanticGraphRegistryService | None = None,
        revision_service: SemanticRevisionService | None = None,
        derived_state_service: SemanticDerivedStateService | None = None,
        lineage_recorder: SemanticLineageRecorder | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.graph_registry = graph_registry or SemanticGraphRegistryService(session, settings)
        self.revision_service = revision_service or SemanticRevisionService(session)
        self.derived_state_service = derived_state_service or SemanticDerivedStateService(
            session, settings
        )
        # Retain injection compatibility for historical callers. The active
        # canonical write path does not construct or invoke a pure lineage
        # collector.
        self.lineage_recorder = lineage_recorder

    def apply_compiled_command(
        self,
        compiled: CompiledCommand,
        *,
        ontology_id: str | None = None,
        actor: str | None = None,
        reason: str | None = None,
        commit: bool = True,
        audit_id: str | None = None,
        fence_attempt_id: str | None = None,
        write_rdf: bool = True,
        modeling_item_effects: dict[tuple[str, str, str, str], list[str]] | None = None,
    ) -> dict[str, Any]:
        """Apply a compiled command with contract guards, revisions and atomic writes."""
        warnings: list[str] = []

        validation_result = self.validate_compiled_command(
            compiled,
            fence_attempt_id=fence_attempt_id,
        )
        if fence_attempt_id is None:
            from app.services.semantic_mapping_state import (
                MappingWriteError,
                require_batch_mapping_write,
            )

            try:
                require_batch_mapping_write(
                    self.session,
                    self.rdf_store,
                    self.settings,
                    compiled.delta,
                    compiled.metadata.get("ontology_id"),
                )
            except MappingWriteError as exc:
                error = CanonicalWriteBlocked(str(exc))
                error.code = exc.code
                raise error from exc

        affected = compiled.delta.affected_graph_iris()
        write_result = (
            self.rdf_store.apply_dataset_delta(compiled.delta)
            if write_rdf
            else GraphWriteResult(
                graph_iri=affected[0] if affected else "",
                applied=True,
                inserted_quad_count=len(compiled.delta.inserts),
                deleted_quad_count=len(compiled.delta.deletes),
            )
        )
        all_warnings = [*warnings, *write_result.warnings]
        audit = self._record_audit(
            compiled=compiled,
            actor=actor,
            reason=reason,
            validation_result=validation_result,
            warnings=all_warnings,
            applied=write_result.applied,
            ontology_id=ontology_id,
            audit_id=audit_id,
        )
        hashes = {}
        if hasattr(self.rdf_store, "get_graph"):
            from rdflib import Graph
            from app.services.ontology_single_graph_migration import model_content_hash
            for iri in affected:
                exists = not hasattr(self.rdf_store, "graph_exists") or self.rdf_store.graph_exists(iri)
                content = self.rdf_store.get_graph(iri, "turtle") if exists else ""
                graph = Graph().parse(data=content, format="turtle") if content else Graph()
                hashes[iri] = model_content_hash(graph)
        changed_graphs = affected if write_result.applied and not compiled.delta.is_empty else []
        revision_bumps = self.revision_service.bump_revisions(
            changed_graphs,
            content_hashes=hashes,
            audit_id=audit.id,
            actor=actor,
        )
        stale_rows = self.derived_state_service.mark_stale_after_edit(
            changed_graphs, audit_id=audit.id, commit=False
        )
        stale_pointers = [
            {
                "result_kind": row.result_kind,
                "run_id": row.run_id,
                "ontology_id": row.ontology_id,
                "result_graph_iri": row.result_graph_iri,
            }
            for row in stale_rows
        ]
        audit.warning_state = {**audit.warning_state, "stale_pointers": stale_pointers}
        if commit:
            self.session.commit()
        result = {
            "audit_id": audit.id,
            "applied": write_result.applied,
            "command_kind": compiled.command_kind,
            "affected_graph_iris": affected,
            "delta": _delta_to_dict(compiled.delta),
            "warnings": all_warnings,
            "validation": validation_result,
            "graph_revisions": revision_bumps,
            "stale_derived_pointers": stale_pointers,
        }
        if commit and write_result.applied:
            ontology_id = compiled.metadata.get("ontology_id")
            result["retrieval_indexes"] = SemanticRetrievalCoordinator(
                self.session, self.rdf_store, self.settings
            ).rebuild_affected(
                affected_graph_iris=affected,
                ontology_ids=[str(ontology_id)] if ontology_id else [],
            )
        else:
            result["retrieval_indexes"] = []
        return result

    def apply_command(
        self,
        command_kind: str,
        payload: dict[str, Any],
        *,
        ontology_id: str | None = None,
        actor: str | None = None,
        reason: str | None = None,
        commit: bool = True,
        audit_id: str | None = None,
        fence_attempt_id: str | None = None,
    ) -> dict[str, Any]:
        """Compile a product command and apply it through the canonical pipeline."""
        if ontology_id:
            if payload.get("ontology_id") not in {None, ontology_id}:
                raise CanonicalSemanticWriteError("ontology_id does not match command scope")
            payload = {**payload, "ontology_id": ontology_id}
        compiled = compile_command(command_kind, payload, self.settings)
        return self.apply_compiled_command(
            compiled,
            ontology_id=ontology_id,
            actor=actor,
            reason=reason,
            commit=commit,
            audit_id=audit_id,
            fence_attempt_id=fence_attempt_id,
        )

    def _require_fence_access(
        self, compiled: CompiledCommand, fence_attempt_id: str | None
    ) -> None:
        ontology_id = compiled.metadata.get("ontology_id")
        if not ontology_id:
            return
        fence = self.session.get(OntologyWriteFenceModel, str(ontology_id))
        if fence is not None and fence.attempt_id != fence_attempt_id:
            raise CanonicalWriteBlocked(
                f"Ontology write is fenced by Modeling Attempt {fence.attempt_id}"
            )

    def validate_compiled_command(
        self,
        compiled: CompiledCommand,
        *,
        fence_attempt_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Run the necessary deterministic contract guards before mutation."""
        self._require_writer_enabled()
        self._lock_ontology(compiled)
        self._require_fence_access(compiled, fence_attempt_id)
        for graph_iri in compiled.delta.affected_graph_iris():
            self._require_managed_graph(graph_iri)
            self._require_editable_graph(graph_iri)
            self._require_direct_editable_category(graph_iri)
        from app.services.semantic_mapping_state import (
            MappingWriteError,
            mapping_state,
            mapping_write_findings,
            mapping_write_relevant,
            project_fence_check,
        )

        ontology_id = compiled.metadata.get("ontology_id")
        try:
            if mapping_write_relevant(
                self.session, self.rdf_store, self.settings, compiled.delta, ontology_id
            ):
                projects, *_ = mapping_state(
                    self.session, self.rdf_store, self.settings, compiled.delta, ontology_id
                )
                project_fence_check(self.session, projects, fence_attempt_id)
            findings = mapping_write_findings(
                self.session, self.rdf_store, self.settings, compiled.delta, ontology_id
            )
            if findings:
                error = CanonicalValidationError(
                    findings[0]["message"], {"conforms": False, "violations": findings}
                )
                error.code = findings[0]["code"]
                raise error
        except MappingWriteError as exc:
            error = CanonicalWriteBlocked(str(exc))
            error.code = exc.code
            raise error from exc
        try:
            validate_operation_delta(self.rdf_store, compiled.delta, self.settings)
        except OperationValidationError as exc:
            error = CanonicalSemanticWriteError(f"{exc.code}: {exc}")
            error.code = exc.code
            raise error from exc
        return None

    def _lock_ontology(self, compiled: CompiledCommand) -> None:
        from app.services.checkpoint_archive import ARCHIVE_KEY, lock_graph_owners

        owners = lock_graph_owners(self.session, compiled.delta.affected_graph_iris())
        if any((owner.external_mappings or {}).get(ARCHIVE_KEY) for owner in owners):
            raise CanonicalWriteBlocked("checkpoint_source_archived: source Project is read-only")
        ontology_id = compiled.metadata.get("ontology_id")
        if ontology_id:
            ontology = self.session.scalar(
                select(OntologyModel).where(OntologyModel.id == str(ontology_id)).with_for_update()
            )
            if ontology and (ontology.external_mappings or {}).get("checkpoint_fork_archive"):
                raise CanonicalWriteBlocked(
                    "checkpoint_source_archived: source Ontology is read-only"
                )

    def compile_only(
        self,
        command_kind: str,
        payload: dict[str, Any],
    ) -> CompiledCommand:
        """Expose the compiler for parity checks without mutating the store."""
        return compile_command(command_kind, payload, self.settings)


    def _require_writer_enabled(self) -> None:
        mode = self.settings.semantic_product_write_mode
        if mode in {"legacy_only", "legacy_primary_rdf_shadow"}:
            raise CanonicalWriteBlocked(
                f"Canonical writer is not enabled in this mode; SEMANTIC_PRODUCT_WRITE_MODE={mode}"
            )

    def _require_managed_graph(self, graph_iri: str) -> None:
        try:
            self.graph_registry.require_managed(graph_iri)
        except GraphRegistryError as exc:
            raise CanonicalSemanticWriteError(str(exc)) from exc

    def _require_editable_graph(self, graph_iri: str) -> None:
        state = self.session.scalar(
            select(SemanticGraphStateModel).where(SemanticGraphStateModel.graph_iri == graph_iri)
        )
        if state is not None and not state.editable:
            raise LockedCanonicalGraph(f"Canonical graph is locked: {graph_iri}")

    def _require_direct_editable_category(self, graph_iri: str) -> None:
        try:
            self.graph_registry.require_direct_editable_category(graph_iri)
        except DirectEditCategoryDenied as exc:
            raise CanonicalSemanticWriteError(str(exc)) from exc
        except GraphRegistryError as exc:
            raise CanonicalSemanticWriteError(str(exc)) from exc


    def _record_audit(
        self,
        *,
        compiled: CompiledCommand,
        actor: str | None,
        reason: str | None,
        validation_result: dict[str, Any] | None,
        warnings: list[str],
        applied: bool,
        ontology_id: str | None,
        audit_id: str | None,
    ) -> SemanticEditAuditModel:
        affected = compiled.delta.affected_graph_iris()
        primary = (
            affected[0]
            if affected
            else (compiled.target_graph_iris[0] if compiled.target_graph_iris else "")
        )
        audit = SemanticEditAuditModel(
            id=audit_id or str(uuid4()),
            actor=actor,
            reason=reason or compiled.command_kind,
            input_format="canonical-write",
            target_graph_iri=primary,
            affected_graph_iris=affected,
            validation_result=validation_result,
            graph_delta=_delta_to_dict(compiled.delta),
            warning_state={
                "warnings": warnings,
                "command_kind": compiled.command_kind,
                "object_kind": compiled.object_kind,
                "source_ids": compiled.source_ids,
                "ontology_id": ontology_id,
            },
            applied=applied,
        )
        self.session.add(audit)
        self.session.flush()
        return audit


_VIOLATION_LIMIT = 20


__all__ = [
    "CanonicalSemanticWriteError",
    "CanonicalSemanticWriteService",
    "CanonicalWriteBlocked",
    "CanonicalValidationError",
    "LockedCanonicalGraph",
]
