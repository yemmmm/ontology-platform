"""Range-controlled, read-only SPARQL query service for external Agents."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from pyparsing import ParseResults
from rdflib import Dataset, Graph, URIRef
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue

from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreRepository, RdfStoreUnavailable
from app.services.semantic_query_scope import (
    SemanticQueryScope,
    SemanticQueryScopeNotReady,
    SemanticQueryScopeResolver,
)


class ScopedSparqlQueryError(RuntimeError):
    status_code = 400
    code = "invalid_query"


_QUERY_FORMS = {
    "SelectQuery": "select",
    "AskQuery": "ask",
    "ConstructQuery": "construct",
    "DescribeQuery": "describe",
}


class ScopedSparqlQueryService:
    def __init__(
        self,
        scope_resolver: SemanticQueryScopeResolver,
        rdf_store: RdfStoreRepository,
        settings: Settings,
    ) -> None:
        self.scope_resolver = scope_resolver
        self.rdf_store = rdf_store
        self.settings = settings

    def query(
        self,
        *,
        project_id: str,
        scope_mode: str,
        ontology_ids: list[str] | None,
        query: str,
        timeout_seconds: float | None = None,
        result_limit: int | None = None,
    ) -> dict[str, Any]:
        query_type = validate_read_only_query(query)
        timeout, limit = _resolve_query_bounds(
            self.settings,
            timeout_seconds=timeout_seconds,
            result_limit=result_limit,
        )
        scope = self.scope_resolver.resolve(
            project_id=project_id,
            scope_mode=scope_mode,
            ontology_ids=ontology_ids,
        )
        if not scope.graph_iris:
            raise SemanticQueryScopeNotReady("Semantic query scope has no queryable graphs")
        scoped_query = inject_dataset_clauses(query, scope.graph_iris, query_type=query_type)
        bounded_query = enforce_top_level_limit(
            scoped_query, max_solutions=limit + 1, query_type=query_type
        )
        result = self.rdf_store.query_sparql(
            bounded_query,
            timeout_seconds=timeout,
            limit=limit + 1,
        )
        _enforce_result_limit(result, query_type=query_type, limit=limit)
        warnings = [*scope.warnings, *_ontology_warnings(scope)]
        if result.truncated:
            warnings.append(
                {"code": "query_truncated", "message": "SPARQL result was truncated."}
            )
        return {
            "result": result.result,
            "result_format": result.result_format,
            "query_type": query_type,
            "scope": scope.public_dict(),
            "truncated": result.truncated,
            "warnings": _dedupe_warnings(warnings),
        }


def validate_read_only_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ScopedSparqlQueryError("SPARQL query must be non-empty")
    if len(query) > 100_000:
        raise ScopedSparqlQueryError("SPARQL query is too long")
    try:
        parsed = parseQuery(query)
    except Exception as exc:
        raise ScopedSparqlQueryError("SPARQL query is invalid") from exc
    root = parsed[1]
    query_type = _QUERY_FORMS.get(getattr(root, "name", ""))
    if query_type is None:
        raise ScopedSparqlQueryError("Only read-only SPARQL queries are allowed")
    if "datasetClause" in root:
        raise ScopedSparqlQueryError("FROM and FROM NAMED are not allowed")
    if _contains_component(root, "ServiceGraphPattern"):
        raise ScopedSparqlQueryError("SERVICE is not allowed")
    return query_type


@dataclass(frozen=True)
class _Token:
    value: str
    start: int
    end: int
    brace_depth: int
    paren_depth: int


def inject_dataset_clauses(
    query: str,
    graph_iris: list[str],
    *,
    query_type: str | None = None,
) -> str:
    """Inject a server-owned RDF dataset at one validated top-level location."""
    query_type = query_type or validate_read_only_query(query)
    if not graph_iris:
        raise ScopedSparqlQueryError("Semantic query scope has no queryable graphs")
    dataset = " ".join(
        f"FROM {URIRef(graph_iri).n3()} FROM NAMED {URIRef(graph_iri).n3()}"
        for graph_iri in graph_iris
    )
    tokens = _scan_tokens(query)
    form_tokens = [
        token
        for token in tokens
        if token.brace_depth == 0
        and token.paren_depth == 0
        and token.value == query_type.upper()
    ]
    if len(form_tokens) != 1:
        raise ScopedSparqlQueryError("Unable to locate a unique top-level SPARQL query form")
    form = form_tokens[0]
    following = [token for token in tokens if token.start >= form.end]

    if query_type in {"select", "ask"}:
        position = _where_or_group_position(following)
    elif query_type == "construct":
        position = _construct_dataset_position(query, following)
    elif query_type == "describe":
        position = _describe_dataset_position(query, following)
    else:
        raise ScopedSparqlQueryError("Only read-only SPARQL queries are allowed")
    if position is None:
        raise ScopedSparqlQueryError("Unable to locate a safe SPARQL dataset position")
    scoped = f"{query[:position].rstrip()} {dataset} {query[position:].lstrip()}"
    try:
        parsed = parseQuery(scoped)
    except Exception as exc:
        raise ScopedSparqlQueryError("Unable to build a safe scoped SPARQL query") from exc
    if _QUERY_FORMS.get(getattr(parsed[1], "name", "")) != query_type:
        raise ScopedSparqlQueryError("Scoped SPARQL query form changed unexpectedly")
    return scoped


def enforce_top_level_limit(
    query: str,
    *,
    max_solutions: int,
    query_type: str,
) -> str:
    """Add or clamp one parsed top-level LIMIT without touching nested syntax."""
    if max_solutions < 1:
        raise ScopedSparqlQueryError("SPARQL solution limit must be positive")
    tokens = _scan_tokens(query)
    top_level = [
        token for token in tokens if token.brace_depth == 0 and token.paren_depth == 0
    ]
    limits = [token for token in top_level if token.value == "LIMIT"]
    if len(limits) > 1:
        raise ScopedSparqlQueryError("Unable to locate a unique top-level SPARQL LIMIT")
    if not limits:
        bounded = f"{query.rstrip()} LIMIT {max_solutions}"
    else:
        limit_token = limits[0]
        value_token = next(
            (token for token in top_level if token.start >= limit_token.end), None
        )
        if value_token is None or not value_token.value.isdigit():
            raise ScopedSparqlQueryError("Unable to locate a safe top-level SPARQL LIMIT value")
        caller_limit = int(value_token.value)
        if caller_limit <= max_solutions:
            bounded = query
        else:
            bounded = (
                f"{query[:value_token.start]}{max_solutions}{query[value_token.end:]}"
            )
    try:
        parsed = parseQuery(bounded)
    except Exception as exc:
        raise ScopedSparqlQueryError("Unable to build a bounded SPARQL query") from exc
    if _QUERY_FORMS.get(getattr(parsed[1], "name", "")) != query_type:
        raise ScopedSparqlQueryError("Bounded SPARQL query form changed unexpectedly")
    return bounded


def _where_or_group_position(tokens: list[_Token]) -> int | None:
    top_level = [
        token for token in tokens if token.brace_depth == 0 and token.paren_depth == 0
    ]
    where = next((token for token in top_level if token.value == "WHERE"), None)
    group = next((token for token in top_level if token.value == "{"), None)
    if where and group and where.start > group.start:
        return None
    boundary = where or group
    return boundary.start if boundary else None


def _construct_dataset_position(query: str, tokens: list[_Token]) -> int | None:
    top_level = [
        token for token in tokens if token.brace_depth == 0 and token.paren_depth == 0
    ]
    first = next((token for token in top_level if token.value in {"WHERE", "{"}), None)
    if first is None:
        return None
    if first.value == "WHERE":
        return first.start
    close = _matching_top_level_brace(tokens, first)
    if close is None:
        return None
    after_template = [token for token in top_level if token.start >= close.end]
    where = next((token for token in after_template if token.value == "WHERE"), None)
    if where is None:
        return None
    between = query[close.end : where.start]
    if between.strip() and not _only_comments(between):
        return None
    return close.end


def _describe_dataset_position(query: str, tokens: list[_Token]) -> int | None:
    boundary = _where_or_group_position(tokens)
    if boundary is not None:
        return boundary
    top_level = [
        token for token in tokens if token.brace_depth == 0 and token.paren_depth == 0
    ]
    modifier = next(
        (
            token
            for token in top_level
            if token.value in {"ORDER", "LIMIT", "OFFSET", "GROUP", "HAVING", "VALUES"}
        ),
        None,
    )
    return modifier.start if modifier else len(query.rstrip())


def _matching_top_level_brace(tokens: list[_Token], opening: _Token) -> _Token | None:
    return next(
        (
            token
            for token in tokens
            if token.value == "}"
            and token.brace_depth == opening.brace_depth
            and token.start > opening.start
        ),
        None,
    )


def _scan_tokens(query: str) -> list[_Token]:
    tokens: list[_Token] = []
    brace_depth = 0
    paren_depth = 0
    index = 0
    while index < len(query):
        char = query[index]
        if char.isspace():
            index += 1
            continue
        if char == "#":
            newline = query.find("\n", index)
            index = len(query) if newline < 0 else newline + 1
            continue
        if char in {'"', "'"}:
            index = _skip_string(query, index)
            continue
        if char in {"?", "$"}:
            index += 1
            while index < len(query) and (query[index].isalnum() or query[index] == "_"):
                index += 1
            continue
        if char == "@":
            index += 1
            while index < len(query) and (query[index].isalnum() or query[index] == "-"):
                index += 1
            continue
        if char == "<" and index + 1 < len(query) and not query[index + 1].isspace():
            index = _skip_iri(query, index)
            continue
        if char == "{":
            tokens.append(_Token("{", index, index + 1, brace_depth, paren_depth))
            brace_depth += 1
            index += 1
            continue
        if char == "}":
            brace_depth -= 1
            if brace_depth < 0:
                raise ScopedSparqlQueryError("Unbalanced SPARQL braces")
            tokens.append(_Token("}", index, index + 1, brace_depth, paren_depth))
            index += 1
            continue
        if char == "(":
            paren_depth += 1
            index += 1
            continue
        if char == ")":
            paren_depth -= 1
            if paren_depth < 0:
                raise ScopedSparqlQueryError("Unbalanced SPARQL parentheses")
            index += 1
            continue
        match = re.match(r"[A-Za-z_][A-Za-z0-9_-]*(?::[A-Za-z0-9_.-]*)?", query[index:])
        if match:
            end = index + len(match.group(0))
            value = match.group(0)
            if ":" in value:
                index = end
                continue
            tokens.append(
                _Token(value.upper(), index, end, brace_depth, paren_depth)
            )
            index = end
            continue
        number = re.match(r"[0-9]+", query[index:])
        if number:
            end = index + len(number.group(0))
            tokens.append(
                _Token(number.group(0), index, end, brace_depth, paren_depth)
            )
            index = end
            continue
        index += 1
    if brace_depth or paren_depth:
        raise ScopedSparqlQueryError("Unbalanced SPARQL delimiters")
    return tokens


def _skip_string(query: str, start: int) -> int:
    quote = query[start]
    triple = query.startswith(quote * 3, start)
    delimiter = quote * (3 if triple else 1)
    index = start + len(delimiter)
    while index < len(query):
        if query[index] == "\\":
            index += 2
            continue
        if query.startswith(delimiter, index):
            return index + len(delimiter)
        index += 1
    raise ScopedSparqlQueryError("Unterminated SPARQL string")


def _skip_iri(query: str, start: int) -> int:
    index = start + 1
    while index < len(query):
        if query[index] == "\\":
            index += 2
            continue
        if query[index] == ">":
            return index + 1
        index += 1
    return start + 1


def _only_comments(text: str) -> bool:
    return not re.sub(r"#.*$", "", text, flags=re.MULTILINE).strip()


def _contains_component(value: Any, component_name: str) -> bool:
    if isinstance(value, CompValue):
        if value.name == component_name:
            return True
        return any(_contains_component(item, component_name) for item in value.values())
    if isinstance(value, (list, tuple, ParseResults)):
        return any(_contains_component(item, component_name) for item in value)
    if isinstance(value, dict):
        return any(_contains_component(item, component_name) for item in value.values())
    return False


def _resolve_query_bounds(
    settings: Settings,
    *,
    timeout_seconds: float | None,
    result_limit: int | None,
) -> tuple[float, int]:
    timeout = (
        settings.semantic_query_timeout_seconds
        if timeout_seconds is None
        else timeout_seconds
    )
    limit = settings.semantic_query_result_limit if result_limit is None else result_limit
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        raise ScopedSparqlQueryError("timeout_seconds must be greater than 0 and at most 120")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10_000:
        raise ScopedSparqlQueryError("result_limit must be between 1 and 10000")
    return float(timeout), limit


def _enforce_result_limit(result: Any, *, query_type: str, limit: int) -> None:
    if query_type == "ask":
        return
    if query_type in {"construct", "describe"}:
        _truncate_rdf_result(result, limit)
        return
    payload = result.result
    if not isinstance(payload, dict):
        return
    bindings = payload.get("results", {}).get("bindings")
    if not isinstance(bindings, list) or len(bindings) <= limit:
        return
    payload["results"]["bindings"] = bindings[:limit]
    result.truncated = True


def _truncate_rdf_result(result: Any, limit: int) -> None:
    if not isinstance(result.result, str):
        return
    content_type = str(result.result_format).lower()
    try:
        if "trig" in content_type:
            source = Dataset()
            source.parse(data=result.result, format="trig")
            quads = sorted(
                source.quads((None, None, None, None)),
                key=lambda quad: tuple(term.n3() for term in quad),
            )
            if len(quads) <= limit:
                return
            bounded = Dataset()
            for subject, predicate, obj, graph in quads[:limit]:
                if graph == source.default_graph.identifier:
                    bounded.default_graph.add((subject, predicate, obj))
                else:
                    bounded.graph(graph).add((subject, predicate, obj))
            result.result = bounded.serialize(format="trig")
        elif "turtle" in content_type:
            source_graph = Graph()
            source_graph.parse(data=result.result, format="turtle")
            triples = sorted(
                source_graph,
                key=lambda triple: tuple(term.n3() for term in triple),
            )
            if len(triples) <= limit:
                return
            bounded_graph = Graph()
            for prefix, namespace in source_graph.namespaces():
                bounded_graph.bind(prefix, namespace)
            for triple in triples[:limit]:
                bounded_graph.add(triple)
            result.result = bounded_graph.serialize(format="turtle")
        else:
            raise ValueError(f"Unsupported RDF query result format: {result.result_format}")
    except Exception as exc:
        raise RdfStoreUnavailable("Unable to enforce SPARQL graph result limit") from exc
    result.truncated = True


def _ontology_warnings(scope: SemanticQueryScope) -> list[dict[str, str]]:
    return [warning for ontology in scope.ontologies for warning in ontology.warnings]


def _dedupe_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for warning in warnings:
        key = (warning["code"], warning["message"])
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result
