"""Read-only SPARQL SELECT runner with graph scoping and timeout."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.scoped_sparql_query import (
    ScopedSparqlQueryError,
    inject_dataset_clauses,
)


class SparqlGuardError(ValueError):
    """Raised when user-provided SPARQL violates the read-only SELECT contract."""


@dataclass(frozen=True)
class SparqlCountResult:
    count: int


_FORBIDDEN_KEYWORDS = (
    "INSERT",
    "DELETE",
    "LOAD",
    "CLEAR",
    "DROP",
    "CREATE",
    "MODIFY",
    "ADD",
    "MOVE",
    "COPY",
)


def _strip_comments(query: str) -> str:
    return re.sub(r"#.*$", "", query, flags=re.MULTILINE)


def _first_keyword(query: str) -> str:
    cleaned = _strip_comments(query).strip()
    if not cleaned:
        return ""
    return cleaned.split(None, 1)[0].upper()


def _validate_select_only(query: str) -> None:
    first = _first_keyword(query)
    if first != "SELECT":
        raise SparqlGuardError("only SELECT allowed")
    upper = _strip_comments(query).upper()
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise SparqlGuardError("only SELECT allowed")


def _scope_query_to_graphs(query: str, graph_iris: list[str]) -> str:
    """Inject the approved RDF dataset into the original SELECT query.

    ``FROM`` provides the approved default graph, and ``FROM NAMED`` limits
    ``GRAPH ?g`` to that same approved graph set.  Keeping the user's SELECT
    as the top-level query preserves its ``?count`` projection and avoids
    embedding a SELECT inside a graph-pattern group.
    """
    try:
        return inject_dataset_clauses(query, graph_iris)
    except ScopedSparqlQueryError as exc:
        raise SparqlGuardError(str(exc)) from exc
    except Exception as exc:
        raise SparqlGuardError("Unable to build a safe scoped SPARQL query") from exc


def run_select_count(
    *,
    store,
    query: str,
    graph_iris: list[str],
    timeout_seconds: float,
) -> SparqlCountResult:
    """Validate, scope, and execute a SPARQL SELECT count query.

    Args:
        store: An object with a query_sparql(query, timeout_seconds, limit) method.
        query: User-provided SPARQL SELECT fragment.
        graph_iris: List of graph IRIs the query is scoped to.
        timeout_seconds: Hard timeout.

    Returns:
        SparqlCountResult with the count from the first binding's 'count' column.

    Raises:
        SparqlGuardError: If query is not a read-only SELECT or is malformed.
    """
    _validate_select_only(query)
    wrapped = _scope_query_to_graphs(query, graph_iris)
    result = store.query_sparql(
        query=wrapped,
        timeout_seconds=timeout_seconds,
        limit=1,
    )
    bindings = []
    if isinstance(result.result, dict):
        bindings = result.result.get("results", {}).get("bindings", []) or []
    if not bindings:
        return SparqlCountResult(count=0)
    row = bindings[0]
    if "count" not in row:
        raise SparqlGuardError("sparql result missing count column")
    return SparqlCountResult(count=int(row["count"]["value"]))
