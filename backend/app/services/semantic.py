from datetime import UTC, datetime
import re
from typing import Any
from uuid import uuid4

from rdflib import Dataset, Graph
from rdflib.compare import to_isomorphic
from rdflib.namespace import RDF
from pyshacl import validate as pyshacl_validate
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticGraphStateModel,
    SemanticProjectionJobModel,
    SemanticReasoningRunModel,
    SemanticValidationRunModel,
)
from app.repositories.rdf_store import (
    DatasetLoadResult,
    RdfFormat,
    RdfStoreRepository,
    SparqlResult,
)
from app.services.owl_reasoner import (
    OwlReasonerResult,
    OwlReasonerRunner,
    ReasonerInputDocument,
)
from app.services.semantic_projection import SemanticProjectionService


class SemanticServiceError(RuntimeError):
    status_code = 400


class ReadOnlySparqlViolation(SemanticServiceError):
    pass


class UnsupportedSemanticEdit(SemanticServiceError):
    pass


class LockedSemanticGraph(SemanticServiceError):
    status_code = 409


class SemanticGraphPolicyViolation(SemanticServiceError):
    status_code = 400


WRITE_SPARQL_OPERATIONS = {"insert", "delete", "load", "clear", "create", "drop", "copy", "move", "add"}


class SemanticService:
    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        reasoner: OwlReasonerRunner | None = None,
        projection: SemanticProjectionService | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.reasoner = reasoner
        self.projection = projection

    def load_dataset(self, content: str, format: str, base_iri: str | None = None) -> DatasetLoadResult:
        _parse_rdf(content, format, base_iri=base_iri or self.settings.semantic_base_iri)
        return self.rdf_store.load_dataset(content, format)

    def query_sparql(
        self,
        query: str,
        timeout_seconds: float | None = None,
        result_limit: int | None = None,
    ) -> SparqlResult:
        if _leading_sparql_operation(query) in WRITE_SPARQL_OPERATIONS:
            raise ReadOnlySparqlViolation("Write SPARQL must use /api/semantic/edits")
        timeout = timeout_seconds or self.settings.semantic_query_timeout_seconds
        limit = result_limit or self.settings.semantic_query_result_limit
        return self.rdf_store.query_sparql(query, timeout, limit)

    def set_graph_editability(
        self,
        graph_iri: str,
        editable: bool,
        actor: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self._require_managed_graph(graph_iri)
        state = self._graph_state(graph_iri)
        if state is None:
            state = SemanticGraphStateModel(id=str(uuid4()), graph_iri=graph_iri)
            self.session.add(state)
        state.editable = editable
        state.updated_by = actor
        state.reason = reason
        state.updated_at = datetime.now(UTC)
        self.session.commit()
        return {
            "graph_iri": graph_iri,
            "editable": state.editable,
            "updated_by": state.updated_by,
            "reason": state.reason,
        }

    def apply_edit(
        self,
        format: str,
        content: str,
        target_graph_iri: str | None = None,
        validate: bool = True,
        shape_graph_iris: list[str] | None = None,
    ) -> dict[str, Any]:
        affected_graphs, update, delta = self._prepare_edit(format, content, target_graph_iri)
        for graph_iri in affected_graphs:
            self._require_managed_graph(graph_iri)
            self._require_editable_graph(graph_iri)

        warnings: list[str] = []
        validation_result: dict[str, Any] | None = None
        if validate and shape_graph_iris:
            validation_result = self.run_validation(
                data_graph_iris=affected_graphs,
                shape_graph_iris=shape_graph_iris,
                inference=self.settings.semantic_shacl_inference,
            )
            if validation_result["conforms"] is False:
                raise SemanticServiceError("Semantic edit candidate does not conform to SHACL shapes")
        elif not validate:
            warnings.append("SHACL validation skipped by request")

        update_result = self.rdf_store.update_sparql(update)
        return {
            "applied": update_result.applied,
            "affected_graph_iris": affected_graphs,
            "delta": delta,
            "warnings": [*warnings, *update_result.warnings],
            "validation": validation_result,
        }

    def export_dataset(self, format: str, graph_iris: list[str] | None = None) -> str:
        return self.rdf_store.export_dataset(format, graph_iris)

    def run_validation(
        self,
        data_graph_iris: list[str],
        shape_graph_iris: list[str],
        inference: str | None = None,
    ) -> dict[str, Any]:
        run = SemanticValidationRunModel(
            id=str(uuid4()),
            data_graph_iris=data_graph_iris,
            shape_graph_iris=shape_graph_iris,
            status="running",
            started_at=datetime.now(UTC),
            run_metadata={"inference": inference or self.settings.semantic_shacl_inference},
        )
        self.session.add(run)
        self.session.commit()
        try:
            data_graph = _combined_graph(self.rdf_store, data_graph_iris)
            shape_graph = _combined_graph(self.rdf_store, shape_graph_iris)
            conforms, report_graph, report_text = pyshacl_validate(
                data_graph,
                shacl_graph=shape_graph,
                inference=inference or self.settings.semantic_shacl_inference,
            )
            summary = _shacl_summary(report_graph)
            run.status = "succeeded"
            run.conforms = bool(conforms)
            run.finished_at = datetime.now(UTC)
            run.run_metadata = {**(run.run_metadata or {}), "summary": summary}
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "conforms": run.conforms,
                "report_text": report_text.decode("utf-8") if isinstance(report_text, bytes) else report_text,
                "summary": summary,
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
                "error": run.error,
            }

    def run_reasoning(
        self,
        source_graph_iris: list[str],
        tasks: list[str],
        persist_result_graph: bool = False,
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        result_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}reasoning-result/{run_id}"
            if persist_result_graph
            else None
        )
        run = SemanticReasoningRunModel(
            id=run_id,
            source_graph_iris=source_graph_iris,
            result_graph_iri=result_graph_iri,
            reasoner=self.settings.semantic_reasoner_command or "unconfigured-command-runner",
            status="running",
            started_at=datetime.now(UTC),
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
                self.rdf_store.update_sparql(_insert_data_update(result_graph_iri, result.inferred_rdf))
            run.status = "succeeded"
            run.consistent = result.consistent
            run.run_metadata = {
                "classification": result.classification,
                "entailments": result.entailments,
                **result.metadata,
            }
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            return _reasoning_response(run, result, result_graph_iri)
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
            }

    def rebuild_projection(
        self,
        source_graph_iris: list[str],
        reasoning_result_graph_iri: str | None = None,
    ) -> dict[str, Any]:
        job = SemanticProjectionJobModel(
            id=str(uuid4()),
            source_graph_iris=source_graph_iris,
            reasoning_result_graph_iri=reasoning_result_graph_iri,
            status="running",
            started_at=datetime.now(UTC),
        )
        self.session.add(job)
        self.session.commit()
        try:
            if not self.settings.semantic_neo4j_projection_enabled:
                raise RuntimeError("Semantic Neo4j projection is disabled")
            if self.projection is None:
                raise RuntimeError("Semantic projection service is not configured")
            result = self.projection.rebuild(
                source_graph_iris,
                reasoning_result_graph_iri=reasoning_result_graph_iri,
                job_id=job.id,
            )
            job.status = "succeeded"
            job.node_count = result.node_count
            job.relationship_count = result.relationship_count
            job.job_metadata = result.metadata
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "job_id": job.id,
                "status": job.status,
                "node_count": job.node_count,
                "relationship_count": job.relationship_count,
                "error": None,
            }
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "job_id": job.id,
                "status": job.status,
                "node_count": 0,
                "relationship_count": 0,
                "error": job.error,
            }

    def _prepare_edit(
        self,
        format: str,
        content: str,
        target_graph_iri: str | None,
    ) -> tuple[list[str], str, dict[str, Any]]:
        if format == "sparql-update":
            return self._prepare_sparql_update(content)
        if format in {RdfFormat.TURTLE.value, RdfFormat.JSON_LD.value}:
            if not target_graph_iri:
                raise UnsupportedSemanticEdit("target_graph_iri is required for Turtle and JSON-LD edits")
            graph = _parse_graph(content, format, base_iri=self.settings.semantic_base_iri)
            update = _triples_to_insert_data(target_graph_iri, graph)
            return [target_graph_iri], update, _graph_delta([target_graph_iri], graph, "insert")
        if format == RdfFormat.TRIG.value:
            dataset = _parse_dataset(content, format, base_iri=self.settings.semantic_base_iri)
            graph_iris = sorted(_dataset_graph_iris(dataset))
            if not graph_iris and target_graph_iri:
                graph = Graph()
                for subject, predicate, obj, _ in dataset.quads((None, None, None, None)):
                    graph.add((subject, predicate, obj))
                update = _triples_to_insert_data(target_graph_iri, graph)
                return [target_graph_iri], update, _graph_delta([target_graph_iri], graph, "insert")
            update = _dataset_to_insert_data(dataset)
            return graph_iris, update, {"operation": "insert", "graph_iris": graph_iris}
        raise UnsupportedSemanticEdit(f"Unsupported semantic edit format: {format}")

    def _prepare_sparql_update(self, update: str) -> tuple[list[str], str, dict[str, Any]]:
        operation = _leading_sparql_operation(update)
        if operation not in {"insert", "delete"} or not re.search(r"\bDATA\b", update, re.IGNORECASE):
            raise UnsupportedSemanticEdit("Phase 1 supports only INSERT DATA and DELETE DATA")
        graph_iris = sorted(set(re.findall(r"\bGRAPH\s*<([^>]+)>", update, flags=re.IGNORECASE)))
        if not graph_iris:
            raise UnsupportedSemanticEdit("SPARQL Update must use explicit GRAPH <iri> blocks")
        return graph_iris, update, {"operation": operation, "graph_iris": graph_iris}

    def _graph_state(self, graph_iri: str) -> SemanticGraphStateModel | None:
        return self.session.scalar(
            select(SemanticGraphStateModel).where(SemanticGraphStateModel.graph_iri == graph_iri)
        )

    def _require_editable_graph(self, graph_iri: str) -> None:
        state = self._graph_state(graph_iri)
        if state is not None and not state.editable:
            raise LockedSemanticGraph(f"Semantic graph is locked: {graph_iri}")

    def _require_managed_graph(self, graph_iri: str) -> None:
        if not graph_iri.startswith(self.settings.semantic_graph_iri_prefix):
            raise SemanticGraphPolicyViolation(
                f"Graph IRI is outside the managed semantic graph prefix: {graph_iri}"
            )


def _parse_rdf(content: str, format: str, base_iri: str) -> None:
    if format == RdfFormat.TRIG.value:
        _parse_dataset(content, format, base_iri)
    else:
        _parse_graph(content, format, base_iri)


def _parse_graph(content: str, format: str, base_iri: str) -> Graph:
    graph = Graph()
    graph.parse(data=content, format=format, publicID=base_iri)
    return graph


def _parse_dataset(content: str, format: str, base_iri: str) -> Dataset:
    dataset = Dataset()
    dataset.parse(data=content, format=format, publicID=base_iri)
    return dataset


def _combined_graph(rdf_store: RdfStoreRepository, graph_iris: list[str]) -> Graph:
    graph = Graph()
    for graph_iri in graph_iris:
        content = rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value)
        graph.parse(data=content, format=RdfFormat.TURTLE.value)
    return graph


def _leading_sparql_operation(query: str) -> str:
    stripped = re.sub(r"(?m)^\s*#.*$", "", query).strip()
    operations = "SELECT|CONSTRUCT|ASK|DESCRIBE|INSERT|DELETE|LOAD|CLEAR|CREATE|DROP|COPY|MOVE|ADD"
    match = re.search(rf"\b({operations})\b", stripped, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _dataset_graph_iris(dataset: Dataset) -> set[str]:
    graph_iris: set[str] = set()
    for subject, predicate, obj, graph in dataset.quads((None, None, None, None)):
        if str(graph.identifier).startswith("urn:x-rdflib:default"):
            continue
        graph_iris.add(str(graph.identifier))
    return graph_iris


def _term(term: Any) -> str:
    return term.n3()


def _triples_to_insert_data(graph_iri: str, graph: Graph) -> str:
    triples = "\n".join(f"{_term(s)} {_term(p)} {_term(o)} ." for s, p, o in graph)
    return f"INSERT DATA {{ GRAPH <{graph_iri}> {{\n{triples}\n}} }}"


def _dataset_to_insert_data(dataset: Dataset) -> str:
    by_graph: dict[str, list[str]] = {}
    for subject, predicate, obj, graph in dataset.quads((None, None, None, None)):
        graph_iri = str(graph.identifier)
        if graph_iri.startswith("urn:x-rdflib:default"):
            continue
        by_graph.setdefault(graph_iri, []).append(f"{_term(subject)} {_term(predicate)} {_term(obj)} .")
    blocks = [f"GRAPH <{graph_iri}> {{\n" + "\n".join(triples) + "\n}" for graph_iri, triples in by_graph.items()]
    return "INSERT DATA {\n" + "\n".join(blocks) + "\n}"


def _insert_data_update(graph_iri: str, inferred_rdf: str) -> str:
    graph = _parse_graph(inferred_rdf, RdfFormat.TURTLE.value, graph_iri)
    return _triples_to_insert_data(graph_iri, graph)


def _graph_delta(graph_iris: list[str], graph: Graph, operation: str) -> dict[str, Any]:
    return {
        "operation": operation,
        "graph_iris": graph_iris,
        "triple_count": len(graph),
        "isomorphic_hash": str(to_isomorphic(graph).graph_digest()),
    }


def _shacl_summary(report_graph: Graph) -> dict[str, int]:
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


def _reasoning_response(
    run: SemanticReasoningRunModel,
    result: OwlReasonerResult,
    result_graph_iri: str | None,
) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "status": run.status,
        "consistent": result.consistent,
        "classification": result.classification,
        "entailments": result.entailments,
        "result_graph_iri": result_graph_iri,
        "error": None,
    }
