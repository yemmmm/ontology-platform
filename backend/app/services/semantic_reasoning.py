"""Graph-set-aware OWL reasoning service.

Extracts Phase 1 reasoning orchestration into its own service so the
SemanticService catch-all can stay focused on edits, exports, and projections.
The reasoning service snapshots input graph revisions, runs the configured OWL
reasoner, persists ``graph/reasoning-result/{run_id}`` when requested,
records missing-evidence warning summaries for data-realization tasks, and
promotes a Phase 4 reasoning pointer only on success.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRevisionModel,
    SemanticReasoningRunModel,
)
from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.owl_reasoner import (
    OwlReasonerResult,
    OwlReasonerRunner,
    ReasonerInputDocument,
)
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_missing_evidence import (
    SemanticMissingEvidenceService,
    derived_warning_message,
)


REASONING_TASKS_WITH_DATA: frozenset[str] = frozenset({"realization", "entailment"})


class SemanticReasoningService:
    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        reasoner: OwlReasonerRunner | None = None,
        graph_set_service: SemanticGraphSetService | None = None,
        derived_state_service: SemanticDerivedStateService | None = None,
        missing_evidence_service: SemanticMissingEvidenceService | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.reasoner = reasoner
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)
        self.derived_state_service = derived_state_service or SemanticDerivedStateService(
            session, settings
        )
        self.missing_evidence_service = missing_evidence_service or (
            SemanticMissingEvidenceService(rdf_store)
        )

    def run_reasoning(
        self,
        source_graph_iris: list[str],
        tasks: list[str],
        persist_result_graph: bool = False,
        graph_set_id: str | None = None,
        engine_version: str | None = None,
        shape_version: str | None = None,
        profile: str = "owl2_dl",
        actor: str | None = None,
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        result_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}reasoning-result/{run_id}"
            if persist_result_graph
            else None
        )
        source_signature = ""
        input_graph_revisions: dict[str, int] = {}
        input_derived_pointers: dict[str, Any] = {}
        if graph_set_id:
            source_signature = self.graph_set_service.source_signature_for(graph_set_id)
            input_graph_revisions = self._revisions_for(source_graph_iris)
            input_derived_pointers = self._current_pointers(graph_set_id)
        run = SemanticReasoningRunModel(
            id=run_id,
            source_graph_iris=source_graph_iris,
            result_graph_iri=result_graph_iri,
            reasoner=self.settings.semantic_reasoner_command or "unconfigured-command-runner",
            status="running",
            started_at=datetime.now(UTC),
            run_metadata={
                "tasks": list(tasks),
                "profile": profile,
                "graph_set_id": graph_set_id,
                "source_signature": source_signature,
                "input_graph_revisions": input_graph_revisions,
                "input_derived_pointers": input_derived_pointers,
                "engine_version": engine_version,
                "shape_version": shape_version,
                "actor": actor,
            },
        )
        self.session.add(run)
        self.session.commit()
        try:
            if self.reasoner is None:
                raise RuntimeError("OWL reasoner runner is not configured")
            documents = [
                ReasonerInputDocument(
                    graph_iri=graph_iri,
                    content=self.rdf_store.get_graph(graph_iri, RdfFormat.TRIG.value),
                )
                for graph_iri in source_graph_iris
            ]
            result = self.reasoner.run(
                documents,
                tasks=tasks,
                timeout_seconds=self.settings.semantic_reasoner_timeout_seconds,
            )
            if persist_result_graph and result.inferred_rdf:
                self.rdf_store.update_sparql(
                    _insert_data_update(result_graph_iri, result.inferred_rdf)
                )
            missing_evidence_summary: dict[str, Any] = {}
            warnings: list[str] = []
            data_aware = bool(REASONING_TASKS_WITH_DATA & set(tasks))
            if data_aware:
                dependencies = self.missing_evidence_service.collect_from_graphs(
                    source_graph_iris
                )
                missing_evidence_summary = (
                    self.missing_evidence_service.summarize_dependencies(dependencies)
                )
                warning = derived_warning_message(dependencies)
                if warning:
                    warnings.append(warning)
            run.status = "succeeded"
            run.consistent = result.consistent
            run.finished_at = datetime.now(UTC)
            run.run_metadata = {
                **run.run_metadata,
                "classification": result.classification,
                "entailments": result.entailments,
                "missing_evidence_dependencies": missing_evidence_summary,
                "warnings": warnings,
                **(result.metadata or {}),
            }
            promoted_pointer: dict[str, Any] | None = None
            if persist_result_graph and graph_set_id:
                pointer = self.derived_state_service.promote_reasoning_pointer(
                    graph_set_id=graph_set_id,
                    run_id=run_id,
                    result_graph_iri=result_graph_iri or "",
                    source_signature=source_signature,
                    engine_name=self.settings.semantic_reasoner_command or "command",
                    engine_version=engine_version,
                    shape_version=shape_version,
                    metadata={
                        "tasks": list(tasks),
                        "profile": profile,
                        "consistent": result.consistent,
                    },
                )
                promoted_pointer = {
                    "graph_set_id": pointer.graph_set_id,
                    "result_kind": pointer.result_kind,
                    "result_graph_iri": pointer.result_graph_iri,
                    "status": pointer.status,
                    "became_current_at": pointer.became_current_at,
                }
                self._mark_rule_pointers_stale_after_reasoning(graph_set_id)
            self.session.commit()
            response = _reasoning_response(run, result, result_graph_iri, missing_evidence_summary, warnings)
            if promoted_pointer:
                response["derived_pointer"] = promoted_pointer
            return response
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "consistent": None,
                "classification": {},
                "entailments": [],
                "result_graph_iri": result_graph_iri,
                "error": run.error,
                "missing_evidence_dependencies": {},
                "warnings": [],
                "input_graph_revisions": input_graph_revisions,
                "source_signature": source_signature,
            }

    def get_reasoning_run(self, run_id: str) -> dict[str, Any]:
        run = self.session.scalar(
            select(SemanticReasoningRunModel).where(
                SemanticReasoningRunModel.id == run_id
            )
        )
        if run is None:
            raise ValueError(f"Reasoning run not found: {run_id}")
        return self._serialize_run(run)

    def list_reasoning_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        graph_set_id: str | None = None,
        kind: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Stage 5 §4.1 — list reasoning runs with optional filters.

        ``graph_set_id`` is read from run metadata (the column itself only
        carries source/result IRIs). ``kind`` matches the reasoning task
        (``consistency``, ``classification``, ``entailment``) which is stored
        as a JSONB list in metadata; we use a containment check so any run
        whose task list includes the requested kind surfaces.
        """
        bounded_limit = max(1, min(limit, 200))
        bounded_offset = max(0, offset)
        statement = select(SemanticReasoningRunModel)
        if graph_set_id:
            statement = statement.where(
                SemanticReasoningRunModel.run_metadata["graph_set_id"].astext
                == graph_set_id
            )
        if kind:
            statement = statement.where(
                SemanticReasoningRunModel.run_metadata["tasks"].astext.contains(kind)
            )
        total = self.session.scalar(
            select(func.count()).select_from(statement.subquery())
        ) or 0
        rows = self.session.scalars(
            statement.order_by(SemanticReasoningRunModel.started_at.desc())
            .offset(bounded_offset)
            .limit(bounded_limit)
        )
        return [self._serialize_run(run) for run in rows], int(total)

    def _serialize_run(self, run: SemanticReasoningRunModel) -> dict[str, Any]:
        metadata = run.run_metadata or {}
        return {
            "run_id": run.id,
            "status": run.status,
            "consistent": run.consistent,
            "classification": metadata.get("classification", {}),
            "entailments": metadata.get("entailments", []),
            "result_graph_iri": run.result_graph_iri,
            "graph_set_id": metadata.get("graph_set_id"),
            "source_signature": metadata.get("source_signature", ""),
            "input_graph_revisions": metadata.get("input_graph_revisions", {}),
            "input_derived_pointers": metadata.get("input_derived_pointers", {}),
            "engine_version": metadata.get("engine_version"),
            "shape_version": metadata.get("shape_version"),
            "tasks": metadata.get("tasks", []),
            "profile": metadata.get("profile", "owl2_dl"),
            "missing_evidence_dependencies": metadata.get(
                "missing_evidence_dependencies", {}
            ),
            "warnings": metadata.get("warnings", []),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error": run.error,
        }

    def _revisions_for(self, graph_iris: list[str]) -> dict[str, int]:
        if not graph_iris:
            return {}
        rows = self.session.scalars(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri.in_(graph_iris)
            )
        )
        return {row.graph_iri: int(row.revision or 0) for row in rows}

    def _current_pointers(self, graph_set_id: str) -> dict[str, Any]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel)
            .where(SemanticDerivedResultPointerModel.graph_set_id == graph_set_id)
            .where(SemanticDerivedResultPointerModel.status == "current")
        )
        return {
            row.result_kind: {
                "run_id": row.run_id,
                "result_graph_iri": row.result_graph_iri,
                "engine_version": row.engine_version,
                "rule_version": row.rule_version,
                "shape_version": row.shape_version,
            }
            for row in rows
        }

    def _mark_rule_pointers_stale_after_reasoning(self, graph_set_id: str) -> None:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel)
            .where(SemanticDerivedResultPointerModel.graph_set_id == graph_set_id)
            .where(SemanticDerivedResultPointerModel.result_kind == "rule")
            .where(SemanticDerivedResultPointerModel.status == "current")
        )
        now = datetime.now(UTC).isoformat()
        for row in rows:
            row.status = "stale"
            row.pointer_metadata = {
                **(row.pointer_metadata or {}),
                "stale_reason": "upstream_reasoning_pointer_changed",
                "stale_at": now,
            }


def _insert_data_update(graph_iri: str, inferred_rdf: str) -> str:
    from rdflib import Graph

    from app.services.semantic import _triples_to_insert_data

    graph = Graph()
    graph.parse(data=inferred_rdf, format=RdfFormat.TURTLE.value, publicID=graph_iri)
    return _triples_to_insert_data(graph_iri, graph)


def _reasoning_response(
    run: SemanticReasoningRunModel,
    result: OwlReasonerResult,
    result_graph_iri: str | None,
    missing_evidence_dependencies: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    metadata = run.run_metadata or {}
    return {
        "run_id": run.id,
        "status": run.status,
        "consistent": result.consistent,
        "classification": result.classification,
        "entailments": result.entailments,
        "result_graph_iri": result_graph_iri,
        "error": None,
        "missing_evidence_dependencies": missing_evidence_dependencies,
        "warnings": warnings,
        "graph_set_id": metadata.get("graph_set_id"),
        "source_signature": metadata.get("source_signature", ""),
        "input_graph_revisions": metadata.get("input_graph_revisions", {}),
        "tasks": metadata.get("tasks", []),
        "profile": metadata.get("profile", "owl2_dl"),
        "engine_version": metadata.get("engine_version"),
        "shape_version": metadata.get("shape_version"),
    }
