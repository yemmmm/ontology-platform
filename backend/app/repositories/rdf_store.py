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


@dataclass
class UpdateResult:
    applied: bool = True
    warnings: list[str] = field(default_factory=list)


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

    def health(self) -> dict[str, str]:
        try:
            response = httpx.get(self.base_url, timeout=3)
        except httpx.RequestError as exc:
            raise RdfStoreUnavailable(str(exc)) from exc
        if response.status_code >= 500:
            raise RdfStoreUnavailable(response.text)
        return {"status": "ok"}


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
