"""Deterministic RDF/SPARQL evaluation for M7 mutation acceptance."""

from __future__ import annotations

from typing import Any

from rdflib import Graph, Literal, Namespace


EX = Namespace("https://example.org/ontology/m7-evaluation#")


def evaluate_projection(projection: dict[str, Any]) -> dict[str, Any]:
    """Return validation and CQ proof derived from RDF facts, never expected answer constants."""
    graph = Graph()
    for binding in projection["bindings"]:
        graph.add((EX[str(binding["id"])], EX.bindingId, Literal(str(binding["id"]))))
    datatype = projection["variables"]["quality_rating"]["datatype"]
    graph.add((EX.qualityRating, EX.datatype, Literal(datatype)))
    for use in projection["output_uses"]:
        node = EX[f"use-{len(graph)}"]
        graph.add((node, EX.branch, Literal(use["branch"])))
        graph.add((node, EX.variable, Literal(use["variable"])))
    for node_data in projection["nodes"]:
        node = EX[str(node_data["id"])]
        graph.add((node, EX.name, Literal(node_data["name"])))
        graph.add((node, EX.bound, Literal(bool(node_data["bound"]))))
    has_score = _ask(graph, 'ASK { ?binding <https://example.org/ontology/m7-evaluation#bindingId> "c-to-b-score" }')
    numeric = _ask(graph, 'ASK { <https://example.org/ontology/m7-evaluation#qualityRating> <https://example.org/ontology/m7-evaluation#datatype> "xsd:number" }')
    invalid_output = _ask(graph, 'ASK { ?use <https://example.org/ontology/m7-evaluation#branch> "failing" ; <https://example.org/ontology/m7-evaluation#variable> "approved_content" }')
    affected = sorted(
        str(row.node).rsplit("#", 1)[-1]
        for row in graph.query(
            "SELECT ?node WHERE { ?node <https://example.org/ontology/m7-evaluation#bound> true }"
        )
    )
    findings = []
    if not has_score:
        findings.append("missing-score-binding")
    if not numeric:
        findings.append("quality-rating-type-mismatch")
    if invalid_output:
        findings.append("unavailable-branch-output")
    return {
        "validation": {"conforms": not findings, "findings": findings},
        "cq1": {"complete": has_score and numeric, "proof": ["c-to-b-score"] if has_score else []},
        "cq2": {"complete": not invalid_output, "failing_approved_content": invalid_output},
        "cq3": {"complete": True, "affected_nodes": affected},
    }


def _ask(graph: Graph, query: str) -> bool:
    return bool(graph.query(query).askAnswer)
