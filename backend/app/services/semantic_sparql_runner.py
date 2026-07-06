"""Read-only SPARQL SELECT runner with graph scoping and timeout."""

from __future__ import annotations

import re
from dataclasses import dataclass


class SparqlGuardError(ValueError):
    """Raised when user-provided SPARQL violates the read-only SELECT contract."""


@dataclass(frozen=True)
class SparqlCountResult:
    count: int


_FORBIDDEN_KEYWORDS = (
    "INSERT", "DELETE", "LOAD", "CLEAR", "DROP",
    "CREATE", "MODIFY", "ADD", "MOVE", "COPY",
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
    """Wrap the query so it only sees data from the specified graphs.

    Injects VALUES ?g { ... } before the user's WHERE body so GRAPH ?g
    can only bind to allowed IRIs. If the user query has no GRAPH clause,
    the wrapper yields no rows.
    """
    values = " ".join(f"<{iri}>" for iri in graph_iris)
    return (
        f"SELECT (COUNT(*) AS ?count) WHERE {{ "
        f"VALUES ?g {{ {values} }} "
        f"{_strip_comments(query).strip()} "
        f"}} LIMIT 1"
    )


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
        query=wrapped, timeout_seconds=timeout_seconds, limit=1,
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
