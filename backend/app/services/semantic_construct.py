"""SPARQL CONSTRUCT execution helpers shared by the construct and rule services.

These helpers run read-only CONSTRUCT queries against the RDF store, enforce
safety limits, and return deterministic statement triples. The CONSTRUCT
result is parsed into RDF triples so callers can attach provenance, evidence
dependencies, and assertion-kind annotations before writing to a rule-result
graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rdflib import Graph

from app.repositories.rdf_store import RdfStoreRepository, SparqlResult


CONSTRUCT_FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "service",
    "insert",
    "delete",
    "load",
    "clear",
    "create",
    "drop",
    "copy",
    "move",
    "add",
    "using",
    "with",
)


@dataclass
class ConstructExecution:
    """Result of executing an approved CONSTRUCT template."""

    statements: list[dict[str, str]] = field(default_factory=list)
    bindings: list[dict[str, str]] = field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    raw: str = ""


def execute_construct_template(
    rdf_store: RdfStoreRepository,
    template: str,
    graph_set_iris: list[str],
    *,
    timeout_seconds: float,
    statement_limit: int,
) -> ConstructExecution:
    """Run an approved CONSTRUCT template and return deterministic statements."""
    validated = validate_approved_construct(
        template,
        graph_set_iris=graph_set_iris,
        statement_limit=statement_limit,
    )
    query = validated
    if " limit " not in f" {query.lower()} ":
        query = f"{query.rstrip()}\nLIMIT {statement_limit}"
    result = rdf_store.query_sparql(query, timeout_seconds=timeout_seconds, limit=statement_limit)
    parsed = _parse_construct_result(result, graph_set_iris=graph_set_iris)
    parsed.truncated = result.truncated or len(parsed.statements) >= statement_limit
    if parsed.truncated:
        parsed.warnings.append("CONSTRUCT result hit the statement limit")
    return parsed


def validate_approved_construct(
    template: str,
    *,
    graph_set_iris: list[str] | None = None,
    statement_limit: int = 10000,
) -> str:
    """Return a normalised template, raising on disallowed clauses."""
    if not isinstance(template, str) or not template.strip():
        raise ConstructTemplateError("CONSTRUCT template must be a non-empty string")
    lowered = template.lower()
    if not re.search(r"\bconstruct\b", lowered):
        raise ConstructTemplateError("CONSTRUCT template must include a CONSTRUCT clause")
    if not re.search(r"\bwhere\b", lowered):
        raise ConstructTemplateError("CONSTRUCT template must include a WHERE clause")
    for keyword in CONSTRUCT_FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise ConstructTemplateError(
                f"CONSTRUCT template may not use '{keyword.upper()}'"
            )
    sanitised = re.sub(r"<[^>]*>", " <iri> ", lowered)
    sanitised = re.sub(r'"[^"]*"', ' "literal" ', sanitised)
    if re.search(r"\w\s*(/|\||\^)\s*\w", sanitised):
        raise ConstructTemplateError(
            "CONSTRUCT templates may not use property path operators in the first Phase 5 pass"
        )
    if re.search(r"[\w>]\s*(\*|\+)\s", sanitised) or re.search(
        r"[\w>]\s*(\*|\+)\s*[\w<{]", sanitised
    ):
        raise ConstructTemplateError(
            "CONSTRUCT templates may not use property path cardinality operators"
        )
    graph_iris_in_template = set(re.findall(r"\bgraph\s*<([^>]+)>", lowered))
    if graph_set_iris is not None:
        allowed = set(graph_set_iris)
        unknown = graph_iris_in_template - allowed
        if unknown:
            raise ConstructTemplateError(
                "CONSTRUCT template references graphs outside the graph set: "
                + ", ".join(sorted(unknown))
            )
    if statement_limit <= 0:
        raise ConstructTemplateError("statement_limit must be positive")
    return template.strip()


def _parse_construct_result(
    result: SparqlResult,
    *,
    graph_set_iris: list[str] | None,
) -> ConstructExecution:
    text = result.result
    if isinstance(text, dict):
        return _parse_construct_json(text)
    if not isinstance(text, str) or not text.strip():
        return ConstructExecution()
    graph = Graph()
    graph.parse(data=text, format="turtle")
    statements: list[dict[str, str]] = []
    bindings: list[dict[str, str]] = []
    for subject, predicate, obj in graph:
        statements.append(
            {
                "s": subject.n3(),
                "p": predicate.n3(),
                "o": obj.n3(),
            }
        )
        if graph_set_iris:
            bindings.append({"graph_set_iris": ",".join(graph_set_iris)})
    return ConstructExecution(statements=statements, bindings=bindings, raw=text)


def _parse_construct_json(payload: dict[str, Any]) -> ConstructExecution:
    bindings = payload.get("results", {}).get("bindings", [])
    statements: list[dict[str, str]] = []
    captures: list[dict[str, str]] = []
    for binding in bindings:
        statements.append(
            {
                "s": binding.get("s", {}).get("value", ""),
                "p": binding.get("p", {}).get("value", ""),
                "o": binding.get("o", {}).get("value", ""),
            }
        )
        captures.append({key: value.get("value", "") for key, value in binding.items()})
    return ConstructExecution(statements=statements, bindings=captures, raw=str(payload))


class ConstructTemplateError(RuntimeError):
    status_code = 400
