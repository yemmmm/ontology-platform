"""Light graph-set visibility labels and evidence redaction.

Phase 6 introduces conservative labels only — not full RBAC. Labels are
declared per graph IRI. A visibility context carries the labels the caller
already holds. Graphs whose label is not in the context are omitted; graphs
labelled ``restricted`` redact evidence text in read APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VisibilityDecision:
    allow: bool
    redact_evidence: bool


class SemanticVisibilityPolicy:
    redacted_marker = "[redacted]"

    def __init__(self, graph_labels: dict[str, str]) -> None:
        self.graph_labels = dict(graph_labels)

    def evaluate(
        self, graph_iri: str, visibility_context: dict[str, Any] | None
    ) -> VisibilityDecision:
        labels = self._context_labels(visibility_context)
        required = self.graph_labels.get(graph_iri)
        if required is None:
            return VisibilityDecision(allow=True, redact_evidence=False)
        if required not in labels:
            return VisibilityDecision(allow=False, redact_evidence=False)
        if required == "restricted":
            return VisibilityDecision(allow=True, redact_evidence=True)
        return VisibilityDecision(allow=True, redact_evidence=False)

    def filter_graphs(
        self,
        graph_iris: list[str],
        visibility_context: dict[str, Any] | None,
    ) -> tuple[list[str], list[dict[str, str]]]:
        kept: list[str] = []
        warnings: list[dict[str, str]] = []
        for iri in graph_iris:
            decision = self.evaluate(iri, visibility_context)
            if decision.allow:
                kept.append(iri)
            else:
                label = self.graph_labels.get(iri, "restricted")
                warnings.append(
                    {
                        "code": "visibility_graph_omitted",
                        "message": f"Graph {iri} omitted (label={label}).",
                    }
                )
        return kept, warnings

    def redact_evidence_text(self, text: str | None) -> str | None:
        if text is None:
            return None
        return self.redacted_marker

    def _context_labels(
        self, visibility_context: dict[str, Any] | None
    ) -> list[str]:
        if not visibility_context:
            return []
        labels = visibility_context.get("labels") or []
        return list(labels)
