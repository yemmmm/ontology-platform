"""Missing-evidence dependency extraction and propagation.

Reads asserted input graphs, finds statements that carry an explicit
``op:evidenceStatus "missing_evidence"`` annotation, and exposes them as
dependencies. The rule execution service marks generated statements that
depend on those inputs with ``op:evidenceStatus "derived_from_missing_evidence"``.
"""

from __future__ import annotations

from typing import Any

from rdflib import Graph

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository


OP_NAMESPACE = "http://ontology-platform.local/ops#"
EVIDENCE_STATUS_PREDICATE = f"{OP_NAMESPACE}evidenceStatus"
DERIVED_FROM_MISSING_EVIDENCE = "derived_from_missing_evidence"
MISSING_EVIDENCE = "missing_evidence"


class SemanticMissingEvidenceService:
    def __init__(self, rdf_store: RdfStoreRepository) -> None:
        self.rdf_store = rdf_store

    def collect_from_graphs(self, graph_iris: list[str]) -> list[dict[str, str]]:
        dependencies: list[dict[str, str]] = []
        for graph_iri in graph_iris:
            content = self.rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value)
            dependencies.extend(self._scan_for_missing_evidence(graph_iri, content))
        return dependencies

    def _scan_for_missing_evidence(self, graph_iri: str, content: str) -> list[dict[str, str]]:
        if not content or not content.strip():
            return []
        graph = Graph()
        graph.parse(data=content, format=RdfFormat.TURTLE.value)
        out: list[dict[str, str]] = []
        for subject, predicate, obj in graph:
            text_obj = str(obj)
            if "missing_evidence" not in text_obj.lower():
                continue
            out.append(
                {
                    "graph_iri": graph_iri,
                    "subject": subject.n3(),
                    "predicate": predicate.n3(),
                    "object": obj.n3(),
                    "evidence_status": MISSING_EVIDENCE,
                }
            )
        return out

    def annotate_generated_statement(self, statement: dict[str, Any]) -> dict[str, Any]:
        statement = dict(statement)
        statement["evidence_status"] = DERIVED_FROM_MISSING_EVIDENCE
        statement.setdefault("warnings", []).append(
            "Statement is derived from input carrying missing-evidence status"
        )
        return statement

    def summarize_dependencies(
        self,
        dependencies: list[dict[str, str]],
    ) -> dict[str, Any]:
        by_graph: dict[str, int] = {}
        for dep in dependencies:
            by_graph[dep["graph_iri"]] = by_graph.get(dep["graph_iri"], 0) + 1
        return {
            "count": len(dependencies),
            "by_graph": by_graph,
            "status": MISSING_EVIDENCE,
            "derived_status": DERIVED_FROM_MISSING_EVIDENCE,
        }


def derived_warning_message(dependencies: list[dict[str, str]]) -> str | None:
    if not dependencies:
        return None
    return (
        "Derived output depends on inputs carrying missing-evidence status; "
        "generated statements annotated as derived_from_missing_evidence"
    )
