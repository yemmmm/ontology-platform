from datetime import UTC, datetime
import re
from typing import Any
from uuid import uuid4

from rdflib import Dataset, Graph, URIRef
from rdflib.compare import to_isomorphic
from rdflib.namespace import RDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticEditAuditModel,
    SemanticGraphStateModel,
)
from app.repositories.rdf_store import (
    DatasetLoadResult,
    RdfFormat,
    RdfGraphDelta,
    RdfStoreRepository,
    SparqlResult,
)
from app.services.semantic_graph_registry import (
    DirectEditCategoryDenied,
    GraphRegistryError,
    SemanticGraphRegistryService,
)
from app.services.semantic_derived_state import (
    SemanticDerivedStateService,
    SemanticRevisionService,
)
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_lineage_recorder import SemanticLineageRecorder
from app.services.semantic_retrieval import SemanticRetrievalCoordinator
from app.services.operation_semantics import (
    OperationValidationError,
    operation_vocabulary,
    validate_operation_delta,
)


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


# Stage 5 §4.5 — patterns for extracting line/column from rdflib parser
# exceptions. ``at line N, column M`` is the canonical rdflib form; ``at
# offset N`` appears for some JSON-LD / TriG failures.
_PARSE_LINE_COLUMN_RE = re.compile(r"at line\s+(\d+)\s*,\s*column\s+(\d+)")
_PARSE_OFFSET_RE = re.compile(r"at offset\s+(\d+)")


WRITE_SPARQL_OPERATIONS = {
    "insert",
    "delete",
    "load",
    "clear",
    "create",
    "drop",
    "copy",
    "move",
    "add",
}


class SemanticService:
    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        graph_registry: SemanticGraphRegistryService | None = None,
        graph_set_service: SemanticGraphSetService | None = None,
        revision_service: SemanticRevisionService | None = None,
        derived_state_service: SemanticDerivedStateService | None = None,
        lineage_recorder: SemanticLineageRecorder | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.graph_registry = graph_registry or SemanticGraphRegistryService(session, settings)
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)
        self.revision_service = revision_service or SemanticRevisionService(session)
        self.derived_state_service = derived_state_service or SemanticDerivedStateService(
            session, settings
        )
        # The legacy recorder remains injectable for old callers, but current
        # semantic writes do not construct or invoke a pure lineage collector.
        self.lineage_recorder = lineage_recorder

    def load_dataset(
        self, content: str, format: str, base_iri: str | None = None
    ) -> DatasetLoadResult:
        _parse_rdf(content, format, base_iri=base_iri or self.settings.semantic_base_iri)
        if format in {RdfFormat.TRIG.value, RdfFormat.N_QUADS.value, RdfFormat.JSON_LD.value}:
            from app.services.checkpoint_archive import ARCHIVE_KEY, lock_graph_owners

            dataset = _parse_dataset(content, format, base_iri or self.settings.semantic_base_iri)
            graph_iris = [
                str(graph.identifier)
                for graph in dataset.graphs()
                if isinstance(graph.identifier, URIRef)
            ]
            owners = lock_graph_owners(self.session, graph_iris)
            if any((owner.external_mappings or {}).get(ARCHIVE_KEY) for owner in owners):
                raise LockedSemanticGraph("checkpoint_source_archived: source Project is read-only")
            from app.services.semantic_mapping_state import (
                MappingWriteError,
                require_batch_mapping_write,
            )

            for graph_iri in graph_iris:
                if self.graph_registry.classify(graph_iri).value == "shapes":
                    raise SemanticGraphPolicyViolation("SHACL Shape maintenance is retired")

            delta = RdfGraphDelta(
                inserts=[
                    (subject.n3(), predicate.n3(), obj.n3(), str(graph.identifier))
                    for graph in dataset.graphs()
                    for subject, predicate, obj in graph
                ]
            )
            try:
                require_batch_mapping_write(self.session, self.rdf_store, self.settings, delta)
            except MappingWriteError as exc:
                error = SemanticServiceError(str(exc))
                error.code = exc.code
                raise error from exc
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
        actor: str | None = None,
        reason: str | None = None,
        warning_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        affected_graphs, update, delta = self._prepare_edit(format, content, target_graph_iri)
        from app.services.checkpoint_archive import ARCHIVE_KEY, lock_graph_owners

        owners = lock_graph_owners(self.session, affected_graphs)
        if any((owner.external_mappings or {}).get(ARCHIVE_KEY) for owner in owners):
            raise LockedSemanticGraph("checkpoint_source_archived: source Project is read-only")
        for graph_iri in affected_graphs:
            self._require_managed_graph(graph_iri)
            self._require_editable_graph(graph_iri)

        restricted_where = format == "sparql-update" and _is_restricted_delete_insert_where(content)
        operation_vocab = operation_vocabulary(self.settings)
        operation_resource_prefix = f"{self.settings.semantic_base_iri.rstrip('/')}/operation/"
        operation_vocab_prefix = operation_vocab["type"].removesuffix("Operation")
        touches_operation_text = (
            any(value in content for value in operation_vocab.values())
            or operation_resource_prefix in content
            or operation_vocab_prefix in content
        )
        current_graph_has_operation = restricted_where and any(
            self._graph_contains_operation(graph_iri, operation_vocab["type"])
            for graph_iri in affected_graphs
        )
        if restricted_where and (touches_operation_text or current_graph_has_operation):
            error = SemanticServiceError(
                "operation_edit_not_deterministic: Operation DELETE/INSERT WHERE must use a deterministic RDF delta"
            )
            error.code = "operation_edit_not_deterministic"
            raise error
        explicit_delta = _lineage_delta_from_edit(
            format=format,
            content=content,
            target_graph_iri=target_graph_iri,
        )
        from app.services.semantic_mapping_state import (
            MappingWriteError,
            require_batch_mapping_write,
        )

        try:
            mapping_delta = explicit_delta
            if explicit_delta.is_empty:
                # The legacy extractor is best-effort. An unprojected raw edit
                # must not hide changes to resources declared by a mapping.
                mapping_delta = RdfGraphDelta(clear_graphs=affected_graphs)
                if re.search(
                    r"(?:[:/])(?:TableMapping|JoinMapping|EnumValueMeaning|MetricDefinition)\b",
                    content,
                ):
                    raise MappingWriteError(
                        "mapping_batch_required",
                        "This raw mapping edit cannot be projected reliably; submit deterministic "
                        "mapping commands through Modeling Batch dry_run/apply_atomic",
                    )
            require_batch_mapping_write(
                self.session,
                self.rdf_store,
                self.settings,
                mapping_delta,
            )
        except MappingWriteError as exc:
            error = SemanticServiceError(str(exc))
            error.code = exc.code
            raise error from exc
        for graph_iri in affected_graphs:
            self._require_direct_editable_category(graph_iri)
        try:
            validate_operation_delta(self.rdf_store, explicit_delta, self.settings)
        except OperationValidationError as exc:
            error = SemanticServiceError(f"{exc.code}: {exc}")
            error.code = exc.code
            raise error from exc

        warnings: list[str] = []
        warning_state = warning_state or {}
        validation_result: dict[str, Any] | None = None
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
        result = {
            "audit_id": audit.id,
            "applied": update_result.applied,
            "affected_graph_iris": affected_graphs,
            "delta": delta,
            "warnings": all_warnings,
            "validation": validation_result,
            "graph_revisions": revision_bumps,
            "stale_derived_pointers": stale_pointers,
        }
        if update_result.applied:
            result["retrieval_indexes"] = SemanticRetrievalCoordinator(
                self.session, self.rdf_store, self.settings
            ).rebuild_affected(affected_graph_iris=affected_graphs)
        else:
            result["retrieval_indexes"] = []
        return result

    def _graph_contains_operation(self, graph_iri: str, operation_type: str) -> bool:
        graph = Graph()
        try:
            content = self.rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value)
            if content and content.strip():
                graph.parse(data=content, format=RdfFormat.TURTLE.value)
        except Exception as exc:
            error = SemanticServiceError(
                "operation_edit_not_deterministic: Current graph could not be inspected before DELETE/INSERT WHERE"
            )
            error.code = "operation_edit_not_deterministic"
            raise error from exc
        return any(graph.triples((None, RDF.type, URIRef(operation_type))))

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
                "warning_state": row.warning_state,
                "applied": row.applied,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def export_dataset(self, format: str, graph_iris: list[str] | None = None) -> str:
        return self.rdf_store.export_dataset(format, graph_iris)


    def _graph_set_source_signature(self, graph_set_id: str) -> str:
        try:
            return self.graph_set_service.source_signature_for(graph_set_id)
        except Exception:
            return ""

    def governance_status(self) -> dict[str, Any]:
        registry_summary = self.graph_registry.status_summary()
        derived_summary = {}
        return {
            "graphs": registry_summary,
            "derived": derived_summary,
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
                raise UnsupportedSemanticEdit(
                    "target_graph_iri is required for Turtle and JSON-LD edits"
                )
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
            graph_iris = sorted(
                set(re.findall(r"\bGRAPH\s*<([^>]+)>", update, flags=re.IGNORECASE))
            )
            return (
                graph_iris,
                update,
                {
                    "operation": "delete_insert_where",
                    "graph_iris": graph_iris,
                    "removed_statements": "where-bound",
                    "inserted_statements": "where-bound",
                },
            )
        if operation not in {"insert", "delete"} or not re.search(
            r"\bDATA\b", update, re.IGNORECASE
        ):
            raise UnsupportedSemanticEdit(
                "Semantic edits support INSERT DATA, DELETE DATA, and restricted DELETE/INSERT WHERE"
            )
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
        raise _parse_error_exception(exc) from exc
    return graph


def _parse_dataset(content: str, format: str, base_iri: str) -> Dataset:
    dataset = Dataset()
    try:
        dataset.parse(data=content, format=format, publicID=base_iri)
    except Exception as exc:
        raise _parse_error_exception(exc) from exc
    return dataset


def _parse_error_exception(exc: BaseException) -> SemanticServiceError:
    """Stage 5 §4.5 — wrap a parser exception with structured line/column.

    The returned ``SemanticServiceError`` carries ``parse_message``,
    ``parse_line`` and ``parse_column`` attributes so callers (notably
    ``/edits``) can populate ``SemanticEditParseError`` on the response without
    re-parsing the exception text.
    """
    message, line, column = _extract_parse_error_details(exc)
    error = SemanticServiceError(f"RDF parse error: {message}")
    error.parse_message = message  # type: ignore[attr-defined]
    error.parse_line = line  # type: ignore[attr-defined]
    error.parse_column = column  # type: ignore[attr-defined]
    return error


def _format_parse_error(exc: BaseException) -> str:
    message, _line, _column = _extract_parse_error_details(exc)
    return f"RDF parse error: {message}"


def _extract_parse_error_details(exc: BaseException) -> tuple[str, int | None, int | None]:
    """Stage 5 §4.5 — extract ``line`` / ``column`` from an rdflib exception.

    rdflib emits two common error formats:

    * ``"... at line N, column M"`` — full position.
    * ``"... at offset N"`` — only an offset; we expose it as ``column`` when
      no line is present (treats single-line input as the common case) and
      leave ``line`` as ``None``.

    Returns ``(message, line, column)`` where ``message`` is the cleaned
    exception text without the leading ``RDF parse error:`` prefix. ``line``
    and ``column`` stay ``None`` when no positional information is present.
    """
    raw = str(exc).strip() or exc.__class__.__name__
    line: int | None = None
    column: int | None = None
    line_column_match = _PARSE_LINE_COLUMN_RE.search(raw)
    if line_column_match:
        line = int(line_column_match.group(1))
        column = int(line_column_match.group(2))
    else:
        offset_match = _PARSE_OFFSET_RE.search(raw)
        if offset_match:
            column = int(offset_match.group(1))
    return raw, line, column


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
        by_graph.setdefault(graph_iri, []).append(
            f"{_term(subject)} {_term(predicate)} {_term(obj)} ."
        )
    blocks = [
        f"GRAPH <{graph_iri}> {{\n" + "\n".join(triples) + "\n}"
        for graph_iri, triples in by_graph.items()
    ]
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


def _lineage_delta_from_edit(
    *,
    format: str,
    content: str,
    target_graph_iri: str | None,
) -> RdfGraphDelta:
    """Best-effort explicit quad delta for direct-edit lineage."""
    delta = RdfGraphDelta()
    if format in {RdfFormat.TURTLE.value, RdfFormat.JSON_LD.value} and target_graph_iri:
        graph = _parse_graph(content, format, base_iri=target_graph_iri)
        delta.inserts.extend(
            (subject.n3(), predicate.n3(), obj.n3(), target_graph_iri)
            for subject, predicate, obj in graph
        )
        return delta
    if format == RdfFormat.TRIG.value:
        dataset = _parse_dataset(content, format, base_iri=target_graph_iri or "")
        for subject, predicate, obj, context in dataset.quads((None, None, None, None)):
            graph_iri = str(context)
            if graph_iri.startswith("urn:x-rdflib:default") and target_graph_iri:
                graph_iri = target_graph_iri
            delta.inserts.append((subject.n3(), predicate.n3(), obj.n3(), graph_iri))
        return delta
    if format != "sparql-update":
        return delta
    if _is_restricted_delete_insert_where(content):
        return _restricted_where_pattern_delta(content)
    blocks = re.findall(
        r"\b(INSERT|DELETE)\s+DATA\s*\{\s*GRAPH\s*<([^>]+)>\s*\{(.*?)\}\s*\}",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    prefixes = "\n".join(
        f"@prefix {prefix}: <{iri}> ."
        for prefix, iri in re.findall(
            r"\bPREFIX\s+([A-Za-z][\w-]*|):\s*<([^>]+)>", content, flags=re.IGNORECASE
        )
    )
    for operation, graph_iri, body in blocks:
        graph = Graph()
        try:
            # SPARQL permits omitting the last triple's dot; Turtle does not.
            body = body.rstrip()
            body = body if body.endswith(".") else body + "\n."
            graph.parse(data=prefixes + "\n" + body, format=RdfFormat.TURTLE.value)
        except Exception:
            continue
        target = delta.inserts if operation.lower() == "insert" else delta.deletes
        target.extend(
            (subject.n3(), predicate.n3(), obj.n3(), graph_iri) for subject, predicate, obj in graph
        )
    return delta


_RESTRICTED_TRIPLE_PATTERN = re.compile(
    r"(<[^>]+>|\?[A-Za-z_][\w-]*|_:[\w-]+)\s+"
    r"(<[^>]+>|\?[A-Za-z_][\w-]*)\s+"
    r"(<[^>]+>|\?[A-Za-z_][\w-]*|_:[\w-]+|"
    r'"(?:\\.|[^"\\])*"(?:@[A-Za-z0-9-]+|\^\^<[^>]+>)?)',
    flags=re.DOTALL,
)


def _restricted_where_pattern_delta(update: str) -> RdfGraphDelta:
    normalized = _strip_sparql_comments(update)
    delete_at = re.search(r"\bDELETE\b", normalized, re.IGNORECASE)
    insert_at = re.search(r"\bINSERT\b", normalized, re.IGNORECASE)
    where_at = re.search(r"\bWHERE\b", normalized, re.IGNORECASE)
    graph_iris = sorted(set(re.findall(r"\bGRAPH\s*<([^>]+)>", normalized, flags=re.IGNORECASE)))
    if not delete_at or not insert_at or not where_at:
        return RdfGraphDelta(clear_graphs=graph_iris)
    delta = RdfGraphDelta()
    for segment, target in (
        (normalized[delete_at.end() : insert_at.start()], delta.deletes),
        (normalized[insert_at.end() : where_at.start()], delta.inserts),
    ):
        for graph_iri, body in re.findall(
            r"\bGRAPH\s*<([^>]+)>\s*\{([^{}]*)\}",
            segment,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            target.extend(
                (match.group(1), match.group(2), match.group(3), graph_iri)
                for match in _RESTRICTED_TRIPLE_PATTERN.finditer(body)
            )
    if not delta.deletes:
        delta.clear_graphs.extend(graph_iris)
    return delta


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
    if re.search(
        r"\b(LOAD|CLEAR|CREATE|DROP|COPY|MOVE|ADD|WITH|USING)\b", normalized, re.IGNORECASE
    ):
        raise UnsupportedSemanticEdit(
            "Restricted DELETE/INSERT WHERE cannot include other update operations"
        )
    if re.search(r"\bGRAPH\s+\?", normalized, re.IGNORECASE):
        raise UnsupportedSemanticEdit(
            "Restricted DELETE/INSERT WHERE must use explicit GRAPH <iri> blocks"
        )
    graph_iris = re.findall(r"\bGRAPH\s*<([^>]+)>", normalized, flags=re.IGNORECASE)
    if len(graph_iris) < 3:
        raise UnsupportedSemanticEdit(
            "Restricted DELETE/INSERT WHERE requires explicit GRAPH <iri> blocks in DELETE, INSERT, and WHERE"
        )
    return True


def _strip_sparql_comments(query: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", query).strip()
