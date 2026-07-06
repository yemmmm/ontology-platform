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
    SemanticEditAuditModel,
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
from app.services.semantic_graph_registry import (
    DirectEditCategoryDenied,
    GraphCategory,
    GraphRegistryError,
    SemanticGraphRegistryService,
)
from app.services.semantic_derived_state import (
    SemanticDerivedStateService,
    SemanticRevisionService,
)
from app.services.semantic_graph_set import SemanticGraphSetService


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
        graph_registry: SemanticGraphRegistryService | None = None,
        graph_set_service: SemanticGraphSetService | None = None,
        revision_service: SemanticRevisionService | None = None,
        derived_state_service: SemanticDerivedStateService | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.reasoner = reasoner
        self.projection = projection
        self.graph_registry = graph_registry or SemanticGraphRegistryService(session, settings)
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)
        self.revision_service = revision_service or SemanticRevisionService(session)
        self.derived_state_service = derived_state_service or SemanticDerivedStateService(
            session, settings
        )

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
        result = self.rdf_store.query_sparql(query, timeout, limit)
        result.warnings.extend(_missing_evidence_read_warnings(result.result))
        return result

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
        actor: str | None = None,
        reason: str | None = None,
        evidence_status: str | None = None,
        warning_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        affected_graphs, update, delta = self._prepare_edit(format, content, target_graph_iri)
        for graph_iri in affected_graphs:
            self._require_managed_graph(graph_iri)
            self._require_editable_graph(graph_iri)
            self._require_direct_editable_category(graph_iri)

        warnings: list[str] = []
        warning_state = warning_state or {}
        evidence_warnings = _missing_evidence_write_warnings(content, delta, evidence_status, warning_state)
        warnings.extend(evidence_warnings)
        validation_result: dict[str, Any] | None = None
        if validate and shape_graph_iris:
            validation_result = self._validate_candidate_graphs(
                affected_graphs,
                shape_graph_iris,
                delta,
                inference=self.settings.semantic_shacl_inference,
            )
            if validation_result["conforms"] is False:
                raise SemanticServiceError("Semantic edit candidate does not conform to SHACL shapes")
        elif not validate:
            warnings.append("SHACL validation skipped by request")

        update_result = self.rdf_store.update_sparql(update)
        all_warnings = [*warnings, *update_result.warnings]
        audit = SemanticEditAuditModel(
            id=str(uuid4()),
            actor=actor,
            reason=reason,
            input_format=format,
            target_graph_iri=target_graph_iri,
            affected_graph_iris=affected_graphs,
            validation_result=validation_result,
            graph_delta=delta,
            evidence_status=evidence_status,
            warning_state={**warning_state, "warnings": all_warnings},
            applied=update_result.applied,
        )
        self.session.add(audit)
        self.session.flush()
        revision_bumps: dict[str, int] = {}
        stale_pointers: list[dict[str, Any]] = []
        try:
            for graph_iri in affected_graphs:
                self.graph_registry.ensure_registered_for_direct_edit(graph_iri, actor=actor)
            revision_bumps = self.revision_service.bump_revisions(
                affected_graphs,
                audit_id=audit.id,
                actor=actor,
            )
            stale_rows = self.derived_state_service.mark_stale_after_edit(
                affected_graphs, audit_id=audit.id
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
        except GraphRegistryError as exc:
            self.session.rollback()
            raise SemanticServiceError(str(exc)) from exc
        audit.warning_state = {**audit.warning_state, "stale_pointers": stale_pointers}
        self.session.commit()
        return {
            "audit_id": audit.id,
            "applied": update_result.applied,
            "affected_graph_iris": affected_graphs,
            "delta": delta,
            "warnings": all_warnings,
            "validation": validation_result,
            "graph_revisions": revision_bumps,
            "stale_derived_pointers": stale_pointers,
        }

    def list_edit_audits(self, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        rows = self.session.scalars(
            select(SemanticEditAuditModel)
            .order_by(SemanticEditAuditModel.created_at.desc())
            .limit(bounded_limit)
        )
        return [
            {
                "id": row.id,
                "actor": row.actor,
                "reason": row.reason,
                "input_format": row.input_format,
                "target_graph_iri": row.target_graph_iri,
                "affected_graph_iris": row.affected_graph_iris,
                "validation_result": row.validation_result,
                "graph_delta": row.graph_delta,
                "evidence_status": row.evidence_status,
                "warning_state": row.warning_state,
                "applied": row.applied,
                "created_at": row.created_at,
            }
            for row in rows
        ]

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
        graph_set_id: str | None = None,
        engine_version: str | None = None,
        shape_version: str | None = None,
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
            promoted_pointer: dict[str, Any] | None = None
            if persist_result_graph and graph_set_id:
                source_signature = self._graph_set_source_signature(graph_set_id)
                pointer = self.derived_state_service.promote_reasoning_pointer(
                    graph_set_id=graph_set_id,
                    run_id=run_id,
                    result_graph_iri=result_graph_iri or "",
                    source_signature=source_signature,
                    engine_name=self.settings.semantic_reasoner_command or "command",
                    engine_version=engine_version,
                    shape_version=shape_version,
                    metadata={
                        "tasks": tasks,
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
                run.run_metadata["graph_set_id"] = graph_set_id
                run.run_metadata["source_signature"] = source_signature
            self.session.commit()
            response = _reasoning_response(run, result, result_graph_iri)
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
            }

    def _graph_set_source_signature(self, graph_set_id: str) -> str:
        try:
            return self.graph_set_service.source_signature_for(graph_set_id)
        except Exception:
            return ""

    def governance_status(self) -> dict[str, Any]:
        registry_summary = self.graph_registry.status_summary()
        derived_summary = self.derived_state_service.status_summary()
        return {
            "graphs": registry_summary,
            "derived": derived_summary,
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
        if _is_restricted_delete_insert_where(update):
            graph_iris = sorted(set(re.findall(r"\bGRAPH\s*<([^>]+)>", update, flags=re.IGNORECASE)))
            return graph_iris, update, {
                "operation": "delete_insert_where",
                "graph_iris": graph_iris,
                "removed_statements": "where-bound",
                "inserted_statements": "where-bound",
            }
        if operation not in {"insert", "delete"} or not re.search(r"\bDATA\b", update, re.IGNORECASE):
            raise UnsupportedSemanticEdit(
                "Semantic edits support INSERT DATA, DELETE DATA, and restricted DELETE/INSERT WHERE"
            )
        graph_iris = sorted(set(re.findall(r"\bGRAPH\s*<([^>]+)>", update, flags=re.IGNORECASE)))
        if not graph_iris:
            raise UnsupportedSemanticEdit("SPARQL Update must use explicit GRAPH <iri> blocks")
        return graph_iris, update, {"operation": operation, "graph_iris": graph_iris}

    def _validate_candidate_graphs(
        self,
        affected_graphs: list[str],
        shape_graph_iris: list[str],
        delta: dict[str, Any],
        inference: str | None,
    ) -> dict[str, Any]:
        if delta.get("operation") != "insert" or not delta.get("inserted_statements"):
            return self.run_validation(affected_graphs, shape_graph_iris, inference)
        data_graph = Graph()
        for graph_iri in affected_graphs:
            if hasattr(self.rdf_store, "graph_exists") and not self.rdf_store.graph_exists(graph_iri):
                continue
            data_graph.parse(
                data=self.rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value),
                format=RdfFormat.TURTLE.value,
            )
        for statement in delta["inserted_statements"]:
            data_graph.add(_statement_from_n3(statement))
        shape_graph = _combined_graph(self.rdf_store, shape_graph_iris)
        conforms, report_graph, report_text = pyshacl_validate(
            data_graph,
            shacl_graph=shape_graph,
            inference=inference or self.settings.semantic_shacl_inference,
        )
        return {
            "run_id": None,
            "status": "succeeded",
            "conforms": bool(conforms),
            "report_text": report_text.decode("utf-8") if isinstance(report_text, bytes) else report_text,
            "summary": _shacl_summary(report_graph),
            "error": None,
            "candidate": True,
        }

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

    def _require_direct_editable_category(self, graph_iri: str) -> None:
        try:
            self.graph_registry.require_direct_editable_category(graph_iri)
        except DirectEditCategoryDenied as exc:
            raise SemanticGraphPolicyViolation(str(exc)) from exc
        except GraphRegistryError as exc:
            raise SemanticGraphPolicyViolation(str(exc)) from exc


def _parse_rdf(content: str, format: str, base_iri: str) -> None:
    if format == RdfFormat.TRIG.value:
        _parse_dataset(content, format, base_iri)
    else:
        _parse_graph(content, format, base_iri)


def _parse_graph(content: str, format: str, base_iri: str) -> Graph:
    graph = Graph()
    try:
        graph.parse(data=content, format=format, publicID=base_iri)
    except Exception as exc:
        raise SemanticServiceError(_format_parse_error(exc)) from exc
    return graph


def _parse_dataset(content: str, format: str, base_iri: str) -> Dataset:
    dataset = Dataset()
    try:
        dataset.parse(data=content, format=format, publicID=base_iri)
    except Exception as exc:
        raise SemanticServiceError(_format_parse_error(exc)) from exc
    return dataset


def _format_parse_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return f"RDF parse error: {message}"


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
    statements = [_statement_to_n3(subject, predicate, obj) for subject, predicate, obj in graph]
    inserted = statements if operation == "insert" else []
    removed = statements if operation == "delete" else []
    return {
        "operation": operation,
        "graph_iris": graph_iris,
        "triple_count": len(graph),
        "isomorphic_hash": str(to_isomorphic(graph).graph_digest()),
        "inserted_statements": inserted,
        "removed_statements": removed,
    }


def _statement_to_n3(subject: Any, predicate: Any, obj: Any) -> str:
    return f"{_term(subject)} {_term(predicate)} {_term(obj)}"


def _statement_from_n3(statement: str) -> tuple[Any, Any, Any]:
    graph = Graph()
    graph.parse(data=f"{statement} .", format=RdfFormat.TURTLE.value)
    return next(iter(graph))


def _is_restricted_delete_insert_where(update: str) -> bool:
    normalized = _strip_sparql_comments(update)
    operation = _leading_sparql_operation(normalized)
    if operation != "delete":
        return False
    if not re.search(r"\bDELETE\b", normalized, re.IGNORECASE):
        return False
    if not re.search(r"\bINSERT\b", normalized, re.IGNORECASE):
        return False
    if not re.search(r"\bWHERE\b", normalized, re.IGNORECASE):
        return False
    if re.search(r"\b(LOAD|CLEAR|CREATE|DROP|COPY|MOVE|ADD|WITH|USING)\b", normalized, re.IGNORECASE):
        raise UnsupportedSemanticEdit("Restricted DELETE/INSERT WHERE cannot include other update operations")
    if re.search(r"\bGRAPH\s+\?", normalized, re.IGNORECASE):
        raise UnsupportedSemanticEdit("Restricted DELETE/INSERT WHERE must use explicit GRAPH <iri> blocks")
    graph_iris = re.findall(r"\bGRAPH\s*<([^>]+)>", normalized, flags=re.IGNORECASE)
    if len(graph_iris) < 3:
        raise UnsupportedSemanticEdit(
            "Restricted DELETE/INSERT WHERE requires explicit GRAPH <iri> blocks in DELETE, INSERT, and WHERE"
        )
    return True


def _strip_sparql_comments(query: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", query).strip()


def _missing_evidence_write_warnings(
    content: str,
    delta: dict[str, Any],
    evidence_status: str | None,
    warning_state: dict[str, Any],
) -> list[str]:
    has_missing_evidence = (
        evidence_status == "missing_evidence"
        or "missing_evidence" in content
        or re.search(r"\bmissingEvidence\b[^\n.]*\btrue\b", content, re.IGNORECASE) is not None
        or any("missing_evidence" in statement for statement in delta.get("inserted_statements", []))
    )
    if not has_missing_evidence:
        return []
    if evidence_status != "missing_evidence":
        raise SemanticGraphPolicyViolation(
            "Missing-evidence semantic writes must declare evidence_status='missing_evidence'"
        )
    if warning_state.get("missing_evidence") is not True:
        raise SemanticGraphPolicyViolation(
            "Missing-evidence semantic writes must include warning_state.missing_evidence=true"
        )
    return ["Semantic edit wrote facts with missing evidence status"]


def _missing_evidence_read_warnings(result: Any) -> list[str]:
    if _contains_missing_evidence(result):
        return ["SPARQL result includes facts with missing evidence status"]
    return []


def _contains_missing_evidence(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("value") == "missing_evidence":
            return True
        for key, item in value.items():
            if key.lower() == "missingevidence" and _binding_is_true(item):
                return True
        return any(_contains_missing_evidence(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_missing_evidence(item) for item in value)
    return value == "missing_evidence"


def _binding_is_true(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("value") in {True, "true", "1"}
    return value is True


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
