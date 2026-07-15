"""Phase 7 canonical semantic write service.

After Phase 7 cutover, both direct semantic edits and structured product command
compilers route through this service so that:

  * graph deltas are validated by SHACL and platform checks once,
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

from pyshacl import validate as pyshacl_validate
from rdflib import Graph
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
    RdfFormat,
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
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_lineage_recorder import SemanticLineageRecorder


class CanonicalSemanticWriteError(RuntimeError):
    status_code = 400


class CanonicalWriteBlocked(CanonicalSemanticWriteError):
    """Raised when the canonical writer is disabled for the current mode."""

    status_code = 409


class LockedCanonicalGraph(CanonicalSemanticWriteError):
    status_code = 409


class CanonicalShaclViolation(CanonicalSemanticWriteError):
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
        graph_set_service: SemanticGraphSetService | None = None,
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
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)
        self.lineage_recorder = lineage_recorder or SemanticLineageRecorder(session)

    def apply_compiled_command(
        self,
        compiled: CompiledCommand,
        *,
        graph_set_id: str | None = None,
        actor: str | None = None,
        reason: str | None = None,
        validate: bool = True,
        shape_graph_iris: list[str] | None = None,
        commit: bool = True,
        audit_id: str | None = None,
        fence_attempt_id: str | None = None,
        write_rdf: bool = True,
        modeling_item_effects: dict[tuple[str, str, str, str], list[str]] | None = None,
    ) -> dict[str, Any]:
        """Apply a compiled product command through the canonical pipeline."""
        warnings: list[str] = []
        evidence_status = compiled.metadata.get("evidence_status")
        if compiled.metadata.get("missing_evidence"):
            warnings.append("Canonical write produced facts with missing evidence status")

        validation_result = self.validate_compiled_command(
            compiled,
            validate_shacl=validate,
            shape_graph_iris=shape_graph_iris,
            fence_attempt_id=fence_attempt_id,
        )
        if not validate:
            warnings.append("SHACL validation skipped by request")

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
            evidence_status=evidence_status,
            validation_result=validation_result,
            warnings=all_warnings,
            applied=write_result.applied,
            graph_set_id=graph_set_id,
            audit_id=audit_id,
        )
        revision_bumps = self.revision_service.bump_revisions(
            affected,
            audit_id=audit.id,
            actor=actor,
        )
        self.lineage_recorder.record_asserted_delta(
            delta=compiled.delta,
            graph_revisions=revision_bumps,
            audit_id=audit.id,
            ontology_id=(
                str(compiled.metadata.get("ontology_id"))
                if compiled.metadata.get("ontology_id")
                else None
            ),
            graph_set_id=graph_set_id,
            modeling_item_effects=modeling_item_effects,
        )
        stale_rows = self.derived_state_service.mark_stale_after_edit(
            affected, audit_id=audit.id, commit=False
        )
        stale_pointers = [
            {
                "result_kind": row.result_kind,
                "run_id": row.run_id,
                "graph_set_id": row.graph_set_id,
                "result_graph_iri": row.result_graph_iri,
            }
            for row in stale_rows
        ]
        audit.warning_state = {**audit.warning_state, "stale_pointers": stale_pointers}
        if commit:
            self.session.commit()
        return {
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

    def apply_command(
        self,
        command_kind: str,
        payload: dict[str, Any],
        *,
        graph_set_id: str | None = None,
        actor: str | None = None,
        reason: str | None = None,
        validate: bool = True,
        shape_graph_iris: list[str] | None = None,
        commit: bool = True,
        audit_id: str | None = None,
        fence_attempt_id: str | None = None,
    ) -> dict[str, Any]:
        """Compile a product command and apply it through the canonical pipeline."""
        compiled = compile_command(command_kind, payload, self.settings)
        return self.apply_compiled_command(
            compiled,
            graph_set_id=graph_set_id,
            actor=actor,
            reason=reason,
            validate=validate,
            shape_graph_iris=shape_graph_iris,
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
        validate_shacl: bool = True,
        shape_graph_iris: list[str] | None = None,
        fence_attempt_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Run every deterministic canonical guard without mutating RDF or SQL."""
        self._require_writer_enabled()
        self._lock_ontology(compiled)
        self._require_fence_access(compiled, fence_attempt_id)
        for graph_iri in compiled.delta.affected_graph_iris():
            self._require_managed_graph(graph_iri)
            self._require_editable_graph(graph_iri)
            self._require_direct_editable_category(graph_iri)
        if validate_shacl and shape_graph_iris:
            result = self._validate_candidate(compiled.delta, shape_graph_iris)
            if result["conforms"] is False:
                raise CanonicalShaclViolation(
                    "Canonical write does not conform to SHACL shapes", result
                )
            return result
        return None

    def _lock_ontology(self, compiled: CompiledCommand) -> None:
        ontology_id = compiled.metadata.get("ontology_id")
        if ontology_id:
            self.session.scalar(
                select(OntologyModel.id)
                .where(OntologyModel.id == str(ontology_id))
                .with_for_update()
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

    def _validate_candidate(
        self,
        delta: RdfGraphDelta,
        shape_graph_iris: list[str],
    ) -> dict[str, Any]:
        candidate = Graph()
        for graph_iri in delta.affected_graph_iris():
            if hasattr(self.rdf_store, "graph_exists") and not self.rdf_store.graph_exists(
                graph_iri
            ):
                continue
            candidate.parse(
                data=self.rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value),
                format=RdfFormat.TURTLE.value,
            )
        shape_graph = Graph()
        shape_targets = set(shape_graph_iris)
        for graph_iri in shape_graph_iris:
            shape_graph.parse(
                data=self.rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value),
                format=RdfFormat.TURTLE.value,
            )
        for subject, predicate, obj, graph_iri in delta.deletes:
            parsed = _triple_from_terms(subject, predicate, obj)
            if parsed is not None:
                candidate.remove(parsed)
                if graph_iri in shape_targets:
                    shape_graph.remove(parsed)
                continue
            subject_term = None if subject.startswith("?") else _term_from_n3(subject)
            predicate_term = None if predicate.startswith("?") else _term_from_n3(predicate)
            object_term = None if obj.startswith("?") else _term_from_n3(obj)
            candidate.remove((subject_term, predicate_term, object_term))
            if graph_iri in shape_targets:
                shape_graph.remove((subject_term, predicate_term, object_term))
        inserts_by_graph: dict[str, list[str]] = {}
        for subject, predicate, obj, graph_iri in delta.inserts:
            inserts_by_graph.setdefault(graph_iri, []).append(f"{subject} {predicate} {obj} .")
        for graph_iri, statements in inserts_by_graph.items():
            inserted = Graph()
            inserted.parse(data="\n".join(statements), format=RdfFormat.TURTLE.value)
            for triple in inserted:
                candidate.add(triple)
                if graph_iri in shape_targets:
                    shape_graph.add(triple)
        conforms, _report_graph, report_text = pyshacl_validate(
            candidate,
            shacl_graph=shape_graph,
            inference=self.settings.semantic_shacl_inference,
        )
        return {
            "conforms": bool(conforms),
            "report_text": report_text.decode("utf-8")
            if isinstance(report_text, bytes)
            else report_text,
            "summary": {"conforms": bool(conforms)},
            "candidate": True,
        }

    def _record_audit(
        self,
        *,
        compiled: CompiledCommand,
        actor: str | None,
        reason: str | None,
        evidence_status: str | None,
        validation_result: dict[str, Any] | None,
        warnings: list[str],
        applied: bool,
        graph_set_id: str | None,
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
            evidence_status=evidence_status,
            warning_state={
                "warnings": warnings,
                "command_kind": compiled.command_kind,
                "object_kind": compiled.object_kind,
                "source_ids": compiled.source_ids,
                "graph_set_id": graph_set_id,
            },
            applied=applied,
        )
        self.session.add(audit)
        self.session.flush()
        return audit


def _triple_from_terms(subject: str, predicate: str, obj: str):
    """Best-effort N3-term parse into an rdflib triple for SHACL candidate build."""
    text = f"{subject} {predicate} {obj} ."
    graph = Graph()
    try:
        graph.parse(data=text, format=RdfFormat.TURTLE.value)
    except Exception:
        return None
    iterator = iter(graph)
    return next(iterator, None)


def _term_from_n3(value: str):
    from rdflib.util import from_n3

    try:
        return from_n3(value)
    except Exception:
        return None


__all__ = [
    "CanonicalSemanticWriteError",
    "CanonicalSemanticWriteService",
    "CanonicalWriteBlocked",
    "CanonicalShaclViolation",
    "LockedCanonicalGraph",
]
