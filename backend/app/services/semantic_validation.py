"""Graph-set-aware SHACL validation service.

Phase 5 separates validation orchestration from the SemanticService catch-all.
The validation service resolves the graph set, fetches RDF graphs through the
RdfStoreRepository, runs pySHACL in the backend, persists
``semantic_validation_runs`` metadata, optionally writes a SHACL report graph
to ``graph/validation-run/{run_id}``, and exposes staleness flags when source
revisions or shape versions change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pyshacl import validate as pyshacl_validate
from rdflib import Graph
from rdflib.namespace import RDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticGraphRevisionModel,
    SemanticValidationRunModel,
)
from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_missing_evidence import (
    SemanticMissingEvidenceService,
    derived_warning_message,
)


VALIDATION_SCOPES: frozenset[str] = frozenset(
    {"asserted_only", "asserted_plus_reasoning"}
)


class SemanticValidationService:
    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        graph_set_service: SemanticGraphSetService | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)
        self.missing_evidence_service = SemanticMissingEvidenceService(rdf_store)

    def run_validation(
        self,
        data_graph_iris: list[str],
        shape_graph_iris: list[str],
        inference: str | None = None,
        graph_set_id: str | None = None,
        validation_scope: str = "asserted_only",
        persist_report_graph: bool = False,
        shape_version: str | None = None,
        engine_version: str | None = None,
        reasoning_result_graph_iri: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        if validation_scope not in VALIDATION_SCOPES:
            raise ValueError(f"Unsupported validation scope: {validation_scope}")
        if validation_scope == "asserted_plus_reasoning" and not reasoning_result_graph_iri:
            raise ValueError(
                "asserted_plus_reasoning validation requires a reasoning_result_graph_iri"
            )
        run_id = str(uuid4())
        source_signature = ""
        input_graph_revisions: dict[str, int] = {}
        if graph_set_id:
            source_signature = self.graph_set_service.source_signature_for(graph_set_id)
            input_graph_revisions = self._revisions_for(
                [*data_graph_iris, *shape_graph_iris]
            )
        report_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}validation-run/{run_id}"
            if persist_report_graph
            else None
        )
        run = SemanticValidationRunModel(
            id=run_id,
            data_graph_iris=data_graph_iris,
            shape_graph_iris=shape_graph_iris,
            status="running",
            started_at=datetime.now(UTC),
            report_graph_iri=report_graph_iri,
            run_metadata={
                "graph_set_id": graph_set_id,
                "source_signature": source_signature,
                "input_graph_revisions": input_graph_revisions,
                "shape_version": shape_version,
                "engine_name": "pyshacl",
                "engine_version": engine_version or _pyshacl_engine_version(),
                "validation_scope": validation_scope,
                "inference": inference or self.settings.semantic_shacl_inference,
                "guidance": {},
                "actor": actor,
            },
        )
        self.session.add(run)
        self.session.commit()
        try:
            data_graph = self._combined_graph(data_graph_iris)
            if validation_scope == "asserted_plus_reasoning" and reasoning_result_graph_iri:
                data_graph.parse(
                    data=self.rdf_store.get_graph(
                        reasoning_result_graph_iri, RdfFormat.TURTLE.value
                    ),
                    format=RdfFormat.TURTLE.value,
                )
            shape_graph = self._combined_graph(shape_graph_iris)
            conforms, report_graph, report_text = pyshacl_validate(
                data_graph,
                shacl_graph=shape_graph,
                inference=inference or self.settings.semantic_shacl_inference,
            )
            summary = _shacl_summary(report_graph)
            guidance = _shape_guidance(shape_graph)
            missing_evidence_inputs = (
                self.missing_evidence_service.collect_from_graphs(data_graph_iris)
            )
            warnings: list[str] = []
            missing_warning = derived_warning_message(missing_evidence_inputs)
            if missing_warning:
                warnings.append(missing_warning)
            if persist_report_graph and report_graph:
                self._persist_report_graph(report_graph_iri, report_graph)
            run.status = "succeeded"
            run.conforms = bool(conforms)
            run.finished_at = datetime.now(UTC)
            run.run_metadata = {
                **run.run_metadata,
                "summary": summary,
                "guidance": guidance,
                "missing_evidence_dependencies": (
                    self.missing_evidence_service.summarize_dependencies(
                        missing_evidence_inputs
                    )
                ),
                "warnings": warnings,
                "report_graph_iri": report_graph_iri,
            }
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "conforms": run.conforms,
                "report_text": (
                    report_text.decode("utf-8")
                    if isinstance(report_text, bytes)
                    else report_text
                ),
                "summary": summary,
                "guidance": guidance,
                "report_graph_iri": report_graph_iri,
                "warnings": warnings,
                "missing_evidence_dependencies": (
                    run.run_metadata["missing_evidence_dependencies"]
                ),
                "graph_set_id": graph_set_id,
                "source_signature": source_signature,
                "input_graph_revisions": input_graph_revisions,
                "shape_version": shape_version,
                "engine_version": run.run_metadata["engine_version"],
                "validation_scope": validation_scope,
                "error": None,
            }
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "conforms": None,
                "report_text": None,
                "summary": {},
                "guidance": {},
                "report_graph_iri": report_graph_iri,
                "warnings": [],
                "missing_evidence_dependencies": {
                    "count": 0,
                    "by_graph": {},
                    "status": "missing_evidence",
                    "derived_status": "derived_from_missing_evidence",
                },
                "graph_set_id": graph_set_id,
                "source_signature": source_signature,
                "input_graph_revisions": input_graph_revisions,
                "shape_version": shape_version,
                "engine_version": run.run_metadata.get("engine_version"),
                "validation_scope": validation_scope,
                "error": run.error,
            }

    def get_validation_run(self, run_id: str) -> dict[str, Any]:
        run = self.session.scalar(
            select(SemanticValidationRunModel).where(
                SemanticValidationRunModel.id == run_id
            )
        )
        if run is None:
            raise ValueError(f"Validation run not found: {run_id}")
        return self._serialize_run(run)

    def list_validation_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, 200))
        rows = self.session.scalars(
            select(SemanticValidationRunModel)
            .order_by(SemanticValidationRunModel.started_at.desc())
            .limit(bounded)
        )
        return [self._serialize_run(run) for run in rows]

    def detect_staleness(self, run: SemanticValidationRunModel) -> dict[str, Any]:
        metadata = run.run_metadata or {}
        graph_set_id = metadata.get("graph_set_id")
        if not graph_set_id:
            return {"stale": False, "reason": "graph_set_agnostic"}
        try:
            current_signature = self.graph_set_service.source_signature_for(graph_set_id)
        except Exception:
            return {"stale": True, "reason": "graph_set_missing"}
        if metadata.get("source_signature") != current_signature:
            return {
                "stale": True,
                "reason": "source_signature_mismatch",
                "current_signature": current_signature,
            }
        current_revisions = self._revisions_for(
            [*run.data_graph_iris, *run.shape_graph_iris]
        )
        if current_revisions != metadata.get("input_graph_revisions"):
            return {
                "stale": True,
                "reason": "input_graph_revisions_changed",
                "current_revisions": current_revisions,
            }
        return {"stale": False, "reason": "current"}

    def _serialize_run(self, run: SemanticValidationRunModel) -> dict[str, Any]:
        metadata = run.run_metadata or {}
        staleness = self.detect_staleness(run)
        return {
            "run_id": run.id,
            "status": run.status,
            "conforms": run.conforms,
            "report_graph_iri": run.report_graph_iri,
            "summary": metadata.get("summary", {}),
            "guidance": metadata.get("guidance", {}),
            "warnings": metadata.get("warnings", []),
            "graph_set_id": metadata.get("graph_set_id"),
            "source_signature": metadata.get("source_signature", ""),
            "input_graph_revisions": metadata.get("input_graph_revisions", {}),
            "shape_version": metadata.get("shape_version"),
            "engine_version": metadata.get("engine_version"),
            "validation_scope": metadata.get("validation_scope", "asserted_only"),
            "missing_evidence_dependencies": metadata.get(
                "missing_evidence_dependencies", {}
            ),
            "staleness": staleness,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error": run.error,
        }

    def _combined_graph(self, graph_iris: list[str]) -> Graph:
        graph = Graph()
        for graph_iri in graph_iris:
            if (
                hasattr(self.rdf_store, "graph_exists")
                and not self.rdf_store.graph_exists(graph_iri)
            ):
                continue
            content = self.rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value)
            if content and content.strip():
                graph.parse(data=content, format=RdfFormat.TURTLE.value)
        return graph

    def _persist_report_graph(self, graph_iri: str, report_graph: Graph) -> None:
        from app.services.semantic import _triples_to_insert_data

        update = _triples_to_insert_data(graph_iri, report_graph)
        self.rdf_store.update_sparql(update)

    def _revisions_for(self, graph_iris: list[str]) -> dict[str, int]:
        if not graph_iris:
            return {}
        rows = self.session.scalars(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri.in_(graph_iris)
            )
        )
        return {row.graph_iri: int(row.revision or 0) for row in rows}


def _pyshacl_engine_version() -> str:
    import pyshacl
    import rdflib

    return f"pyshacl={getattr(pyshacl, '__version__', 'unknown')};rdflib={rdflib.__version__}"


def _shacl_summary(report_graph: Graph) -> dict[str, Any]:
    from rdflib.namespace import SH

    counts = {"violations": 0, "warnings": 0, "info": 0}
    for result in report_graph.subjects(predicate=RDF.type, object=SH.ValidationResult):
        severities = list(report_graph.objects(result, SH.resultSeverity))
        if SH.Violation in severities:
            counts["violations"] += 1
        elif SH.Warning in severities:
            counts["warnings"] += 1
        elif SH.Info in severities:
            counts["info"] += 1
    return counts


def _shape_guidance(shape_graph: Graph) -> dict[str, Any]:
    """Surface minimal UI/form guidance from a shape graph."""
    from rdflib.namespace import SH

    guidance: dict[str, Any] = {
        "required_properties": [],
        "datatype_constraints": [],
    }
    for shape in shape_graph.subjects(predicate=RDF.type, object=SH.NodeShape):
        for property_shape in shape_graph.objects(shape, SH.property):
            path = shape_graph.value(property_shape, SH.path)
            min_count = shape_graph.value(property_shape, SH.minCount)
            datatype = shape_graph.value(property_shape, SH.datatype)
            if path is not None and min_count is not None and int(min_count) > 0:
                guidance["required_properties"].append(str(path))
            if path is not None and datatype is not None:
                guidance["datatype_constraints"].append(
                    {"path": str(path), "datatype": str(datatype)}
                )
    return guidance
