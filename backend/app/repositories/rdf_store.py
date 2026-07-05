from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx


class RdfFormat(StrEnum):
    TURTLE = "turtle"
    TRIG = "trig"
    JSON_LD = "json-ld"
    N_QUADS = "n-quads"


CONTENT_TYPES: dict[str, str] = {
    RdfFormat.TURTLE.value: "text/turtle",
    RdfFormat.TRIG.value: "application/trig",
    RdfFormat.JSON_LD.value: "application/ld+json",
    RdfFormat.N_QUADS.value: "application/n-quads",
}


class RdfStoreError(RuntimeError):
    status_code = 502


class RdfStoreUnavailable(RdfStoreError):
    pass


class UnsupportedRdfFormat(RdfStoreError):
    status_code = 400


class RdfParseFailure(RdfStoreError):
    status_code = 400


class SparqlSyntaxFailure(RdfStoreError):
    status_code = 400


class SparqlQueryTimeout(RdfStoreError):
    status_code = 504


class SparqlResultTooLarge(RdfStoreError):
    status_code = 413


class SparqlUpdateRejected(RdfStoreError):
    status_code = 400


class GraphHashMismatch(RdfStoreError):
    """Raised when a hash-guarded replacement detects a concurrent write."""

    status_code = 409


@dataclass
class DatasetLoadResult:
    loaded: bool
    format: str
    graph_count: int | None = None
    triple_count: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class SparqlResult:
    result: Any
    result_format: str = "application/sparql-results+json"
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    applied: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class GraphWriteResult:
    graph_iri: str
    applied: bool = True
    previous_hash: str | None = None
    new_hash: str | None = None
    inserted_quad_count: int | None = None
    deleted_quad_count: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class GraphDropResult:
    graph_iri: str
    dropped: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class RdfGraphDelta:
    """A scoped set of insert/delete operations against named graphs.

    Phase 7 canonical write path and migration writer both produce deltas in this
    shape so that audit, idempotency, and graph revision updates share one type.
    """

    inserts: list[tuple[str, str, str, str]] = field(default_factory=list)
    deletes: list[tuple[str, str, str, str]] = field(default_factory=list)
    clear_graphs: list[str] = field(default_factory=list)
    drop_graphs: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.inserts
            or self.deletes
            or self.clear_graphs
            or self.drop_graphs
        )

    def affected_graph_iris(self) -> list[str]:
        iris: list[str] = []
        seen: set[str] = set()
        for quad in (*self.inserts, *self.deletes):
            graph_iri = quad[3]
            if graph_iri not in seen:
                seen.add(graph_iri)
                iris.append(graph_iri)
        for graph_iri in (*self.clear_graphs, *self.drop_graphs):
            if graph_iri not in seen:
                seen.add(graph_iri)
                iris.append(graph_iri)
        return iris




class RdfStoreRepository:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def load_dataset(self, content: str | bytes, format: str) -> DatasetLoadResult:
        content_type = _content_type(format)
        try:
            response = httpx.post(
                f"{self.base_url}/store",
                content=content,
                headers={"content-type": content_type},
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        _raise_for_rdf_response(response, parse_error=RdfParseFailure)
        return DatasetLoadResult(loaded=True, format=format)

    def query_sparql(self, query: str, timeout_seconds: float, limit: int) -> SparqlResult:
        effective_query = _query_with_limit(query, limit)
        try:
            response = httpx.post(
                f"{self.base_url}/query",
                data={"query": effective_query},
                headers={"accept": "application/sparql-results+json, text/turtle, application/trig"},
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SparqlQueryTimeout("SPARQL query timed out") from exc
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        _raise_for_rdf_response(response, parse_error=SparqlSyntaxFailure)
        content_type = response.headers.get("content-type", "application/sparql-results+json")
        if "json" in content_type:
            return SparqlResult(result=response.json(), result_format=content_type)
        return SparqlResult(result=response.text, result_format=content_type)

    def update_sparql(self, update: str) -> UpdateResult:
        try:
            response = httpx.post(
                f"{self.base_url}/update",
                data={"update": update},
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        _raise_for_rdf_response(response, parse_error=SparqlUpdateRejected)
        return UpdateResult()

    def export_dataset(self, format: str, graph_iris: list[str] | None = None) -> str:
        if graph_iris:
            graph_values = " ".join(f"<{graph_iri}>" for graph_iri in graph_iris)
            query = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH ?g {{ ?s ?p ?o }} VALUES ?g {{ {graph_values} }} }}"
            result = self.query_sparql(query, timeout_seconds=30, limit=100000)
            return str(result.result)
        content_type = _content_type(format)
        try:
            response = httpx.get(
                f"{self.base_url}/store",
                headers={"accept": content_type},
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        _raise_for_rdf_response(response, parse_error=RdfParseFailure)
        return response.text

    def get_graph(self, graph_iri: str, format: str) -> str:
        content_type = _content_type(format)
        try:
            response = httpx.get(
                f"{self.base_url}/store",
                params={"graph": graph_iri},
                headers={"accept": content_type},
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        _raise_for_rdf_response(response, parse_error=RdfParseFailure)
        return response.text

    def graph_exists(self, graph_iri: str) -> bool:
        query = f"ASK {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}"
        result = self.query_sparql(query, timeout_seconds=10, limit=1)
        if isinstance(result.result, dict):
            return bool(result.result.get("boolean"))
        return False

    def clear_graph(self, graph_iri: str) -> UpdateResult:
        """Drop all triples in the named graph but keep the graph context.

        Uses a graph-scoped DELETE WHERE so other graphs are not affected.
        """
        update = f"DROP SILENT GRAPH <{graph_iri}>"
        return self.update_sparql(update)

    def drop_named_graph(self, graph_iri: str) -> GraphDropResult:
        """Drop a named graph and its contents entirely.

        Distinct from ``clear_graph`` because callers (migration rollback, graph
        GC) treat drop as a destructive operation that must be recorded as a
        graph-removal rather than a content reset.
        """
        self.update_sparql(f"DROP SILENT GRAPH <{graph_iri}>")
        return GraphDropResult(graph_iri=graph_iri, dropped=True)

    def export_named_graph(self, graph_iri: str, format: str) -> str:
        """Return the named graph serialized in the requested format."""
        return self.get_graph(graph_iri, format)

    def put_named_graph(self, graph_iri: str, content: str, format: str) -> GraphWriteResult:
        """Replace the named graph atomically with the supplied content.

        Oxigraph's SPARQL 1.1 HTTP graph protocol exposes PUT to ``/store?graph=``
        as a graph-scoped replacement; we use it so that concurrent writers cannot
        interleave statements from the previous and incoming payloads.
        """
        previous_hash = self.graph_content_hash(graph_iri)
        content_type = _content_type(format)
        try:
            response = httpx.put(
                f"{self.base_url}/store",
                params={"graph": graph_iri},
                content=content,
                headers={"content-type": content_type},
                timeout=60,
            )
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        _raise_for_rdf_response(response, parse_error=RdfParseFailure)
        new_hash = self.graph_content_hash(graph_iri)
        return GraphWriteResult(
            graph_iri=graph_iri,
            applied=True,
            previous_hash=previous_hash,
            new_hash=new_hash,
        )

    def replace_named_graph_if_hash_matches(
        self,
        graph_iri: str,
        content: str,
        format: str,
        expected_previous_hash: str | None,
    ) -> GraphWriteResult:
        """Replace the named graph only when the current hash matches expectation.

        Phase 7 idempotent rerun and shadow backfill rely on this guard to make
        every batch safe to retry. When the store is empty for the graph and the
        caller also expects ``None``, the replacement still proceeds.
        """
        observed = self.graph_content_hash(graph_iri)
        if observed != expected_previous_hash:
            raise GraphHashMismatch(
                f"Graph {graph_iri} hash mismatch: expected "
                f"{expected_previous_hash!r}, observed {observed!r}"
            )
        result = self.put_named_graph(graph_iri, content, format)
        result.previous_hash = observed
        return result

    def apply_dataset_delta(self, delta: RdfGraphDelta) -> GraphWriteResult:
        """Apply an insert/delete/clear/drop delta as a single SPARQL Update.

        Combines all operations into one request so partial failures leave the
        store in a deterministic state and graph revisions increment once per
        logical change.
        """
        if delta.is_empty:
            return GraphWriteResult(graph_iri="", applied=False)
        parts: list[str] = []
        if delta.drop_graphs:
            parts.extend(f"DROP SILENT GRAPH <{iri}>" for iri in delta.drop_graphs)
        if delta.clear_graphs:
            parts.extend(f"CLEAR SILENT GRAPH <{iri}>" for iri in delta.clear_graphs)
        if delta.deletes:
            grouped: dict[str, list[tuple[str, str, str]]] = {}
            for subject, predicate, obj, graph_iri in delta.deletes:
                grouped.setdefault(graph_iri, []).append((subject, predicate, obj))
            for graph_iri, triples in grouped.items():
                block = " . ".join(
                    f"{subject} {predicate} {obj}" for subject, predicate, obj in triples
                )
                parts.append(f"DELETE DATA {{ GRAPH <{graph_iri}> {{ {block} }} }}")
        if delta.inserts:
            grouped_inserts: dict[str, list[tuple[str, str, str]]] = {}
            for subject, predicate, obj, graph_iri in delta.inserts:
                grouped_inserts.setdefault(graph_iri, []).append((subject, predicate, obj))
            for graph_iri, triples in grouped_inserts.items():
                block = " . ".join(
                    f"{subject} {predicate} {obj}" for subject, predicate, obj in triples
                )
                parts.append(f"INSERT DATA {{ GRAPH <{graph_iri}> {{ {block} }} }}")
        update = " ;\n".join(parts)
        self.update_sparql(update)
        affected = delta.affected_graph_iris()
        primary = affected[0] if affected else ""
        return GraphWriteResult(
            graph_iri=primary,
            applied=True,
            inserted_quad_count=len(delta.inserts),
            deleted_quad_count=len(delta.deletes) + len(delta.clear_graphs) + len(delta.drop_graphs),
        )

    def graph_content_hash(self, graph_iri: str) -> str | None:
        """Return a deterministic content hash for the graph or None when empty."""
        query = (
            f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}"
        )
        result = self.query_sparql(query, timeout_seconds=30, limit=100000)
        text = result.result
        if not text:
            return None
        if isinstance(text, dict):
            text = str(text)
        if not text.strip():
            return None
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def health(self) -> dict[str, str]:
        try:
            response = httpx.get(self.base_url, timeout=3)
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        if response.status_code >= 500:
            raise RdfStoreUnavailable(response.text)
        return {"status": "ok"}

    def query_read_model(
        self,
        query: str,
        graph_iris: list[str],
        timeout_seconds: float,
        limit: int,
    ) -> SparqlResult:
        """Bounded SPARQL SELECT helper used by Phase 6 read models.

        Read-only. The list of graph IRIs is recorded as a comment in the
        query text so test fakes can identify the requested scope without
        requiring the SPARQL parser to know about them.
        """
        bounded = (
            f"{query.rstrip()}\n"
            f"# bounded_limit={int(limit)} timeout={float(timeout_seconds)} "
            f"graphs={','.join(graph_iris)}"
        )
        return self.query_sparql(bounded, timeout_seconds=timeout_seconds, limit=int(limit))


def _content_type(format: str) -> str:
    try:
        return CONTENT_TYPES[format]
    except KeyError as exc:
        raise UnsupportedRdfFormat(f"Unsupported RDF format: {format}") from exc


def _raise_for_rdf_response(response: httpx.Response, parse_error: type[RdfStoreError]) -> None:
    if response.status_code < 400:
        return
    if response.status_code in {400, 422}:
        raise parse_error(response.text)
    if response.status_code == 408:
        raise SparqlQueryTimeout(response.text)
    raise RdfStoreUnavailable(response.text)


def _query_with_limit(query: str, limit: int) -> str:
    if " limit " in f" {query.lower()} ":
        return query
    return f"{query.rstrip()}\nLIMIT {limit}"
