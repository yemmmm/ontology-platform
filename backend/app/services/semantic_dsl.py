"""Platform DSL compiler and executor.

The DSL is intentionally small: when/then lists with triple patterns and
scalar filters. The compiler turns a DSL program into a deterministic SPARQL
SELECT with a VALUES clause that captures matched bindings, then materialises
output triples using string templating.

The compiler does not accept arbitrary Python or JavaScript. Property paths
and named graph IRIs outside the supplied graph-set membership are rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rdflib import Graph

from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_construct import ConstructTemplateError


DSL_VARIABLE_PATTERN = re.compile(r"^\?([A-Za-z_][A-Za-z0-9_]*)$")


@dataclass
class DslExecution:
    statements: list[dict[str, str]] = field(default_factory=list)
    bindings: list[dict[str, str]] = field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    missing_evidence_inputs: list[dict[str, str]] = field(default_factory=list)


def compile_dsl_to_select(
    body: dict[str, Any],
    *,
    graph_set_iris: list[str],
    statement_limit: int,
) -> str:
    when = body["when"]
    then = body["then"]
    if not graph_set_iris:
        raise ConstructTemplateError("DSL rules require at least one graph-set member")
    graph_values = " ".join(f"<{iri}>" for iri in graph_set_iris)
    where_parts: list[str] = []
    project_vars: set[str] = set()
    for clause in when:
        if "filter" in clause:
            where_parts.append(_compile_filter(clause["filter"]))
            continue
        subject_var = _term_or_literal(clause["s"], project_vars)
        predicate_term = _term_or_literal(clause["p"], project_vars)
        object_term = _term_or_literal(clause["o"], project_vars)
        where_parts.append(f"  {subject_var} {predicate_term} {object_term} .")
    then_subjects = {clause["s"] for clause in then}
    then_objects = {clause["o"] for clause in then}
    for variable in [*then_subjects, *then_objects]:
        if variable.startswith("?"):
            project_vars.add(variable[1:])
    select_vars = sorted(project_vars)
    if not select_vars:
        raise ConstructTemplateError("DSL program must project at least one variable")
    select_clause = "SELECT DISTINCT " + " ".join(f"?{name}" for name in select_vars)
    values_clause = f"VALUES ?g {{ {graph_values} }}"
    where_block = "GRAPH ?g {\n" + "\n".join(where_parts) + "\n}"
    query = (
        f"{select_clause}\n"
        f"WHERE {{\n  {values_clause}\n  {where_block}\n}}"
    )
    if statement_limit > 0:
        query += f"\nLIMIT {statement_limit}"
    return query


def execute_dsl(
    rdf_store: RdfStoreRepository,
    body: dict[str, Any],
    *,
    graph_set_iris: list[str],
    timeout_seconds: float,
    statement_limit: int,
    missing_evidence_inputs: list[dict[str, str]] | None = None,
) -> DslExecution:
    if statement_limit <= 0:
        raise ConstructTemplateError("statement_limit must be positive")
    select_query = compile_dsl_to_select(
        body,
        graph_set_iris=graph_set_iris,
        statement_limit=statement_limit,
    )
    result = rdf_store.query_sparql(
        select_query, timeout_seconds=timeout_seconds, limit=statement_limit
    )
    payload = result.result if isinstance(result.result, dict) else {}
    bindings = payload.get("results", {}).get("bindings", [])
    execution = materialise_dsl_bindings(
        body,
        bindings,
        missing_evidence_inputs=missing_evidence_inputs or [],
    )
    execution.truncated = result.truncated or len(bindings) >= statement_limit
    if execution.truncated:
        execution.warnings.append("DSL execution hit the statement limit")
    return execution


def materialise_dsl_bindings(
    body: dict[str, Any],
    bindings: list[dict[str, Any]],
    *,
    missing_evidence_inputs: list[dict[str, str]] | None = None,
) -> DslExecution:
    then = body["then"]
    explain = body.get("explain")
    execution = DslExecution(missing_evidence_inputs=missing_evidence_inputs or [])
    seen: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(bindings):
        resolved = {key: _binding_value(value) for key, value in binding.items()}
        for template in then:
            statement = _materialise_statement(template, resolved)
            key = (statement["s"], statement["p"], statement["o"])
            if key in seen:
                continue
            seen.add(key)
            record = dict(statement)
            record["binding_index"] = str(index)
            if explain:
                record["explanation"] = str(explain)
            if missing_evidence_inputs:
                record["derived_from_missing_evidence"] = "true"
            execution.statements.append(record)
        execution.bindings.append({key: str(value) for key, value in resolved.items()})
    return execution


def _materialise_statement(template: dict[str, Any], binding: dict[str, Any]) -> dict[str, str]:
    return {
        "s": _resolve_template_term(template["s"], binding),
        "p": _resolve_template_term(template["p"], binding),
        "o": _resolve_template_term(template["o"], binding),
    }


def _resolve_template_term(term: str, binding: dict[str, Any]) -> str:
    if isinstance(term, str) and term.startswith("?"):
        variable = term[1:]
        return binding.get(variable, term)
    return str(term)


def _binding_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return str(value)


def _term_or_literal(term: str, project_vars: set[str]) -> str:
    if isinstance(term, str) and DSL_VARIABLE_PATTERN.match(term):
        project_vars.add(term[1:])
        return term
    if isinstance(term, str):
        if term.startswith("<") and term.endswith(">"):
            return term
        if term.startswith('"') and term.endswith('"'):
            return term
    return term


def _compile_filter(filter_clause: dict[str, Any]) -> str:
    operator, args = next(iter(filter_clause.items()))
    if operator not in {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"}:
        raise ConstructTemplateError(f"Unsupported DSL filter operator: {operator}")
    if not isinstance(args, list) or len(args) < 2:
        raise ConstructTemplateError(f"DSL filter '{operator}' needs two operands")
    if operator in {"in", "not_in"}:
        operand, *values = args
        rendered_values = " ".join(_render_filter_value(value) for value in values)
        return f"FILTER ({_render_filter_value(operand)} {'IN' if operator == 'in' else 'NOT IN'} ({rendered_values}))"
    op_map = {
        "eq": "=",
        "neq": "!=",
        "lt": "<",
        "lte": "<=",
        "gt": ">",
        "gte": ">=",
    }
    return (
        f"FILTER({_render_filter_value(args[0])} {op_map[operator]} "
        f"{_render_filter_value(args[1])})"
    )


def _render_filter_value(value: Any) -> str:
    if isinstance(value, str) and value.startswith("?"):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if value.startswith('"') and value.endswith('"'):
            return value
        return f'"{value}"'
    raise ConstructTemplateError(f"Unsupported DSL filter operand: {value!r}")


def parse_graph_for_missing_evidence(content: str) -> list[dict[str, str]]:
    """Return RDF-star-like annotations of missing-evidence input statements."""
    graph = Graph()
    if not content.strip():
        return []
    graph.parse(data=content, format="turtle")
    statements: list[dict[str, str]] = []
    for subject, predicate, obj in graph:
        if "missingEvidence" in str(obj) or "missing_evidence" in str(obj):
            statements.append(
                {
                    "s": subject.n3(),
                    "p": predicate.n3(),
                    "o": obj.n3(),
                }
            )
    return statements
