"""Resolve an Ontology to its single internal RDF storage location."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.repositories.models import OntologyModel, OntologyWriteFenceModel


class ReadScopeError(RuntimeError):
    status_code = 400


@dataclass
class ScopeResolution:
    ontology_id: str
    model_revision: int
    include: str
    model_graph_iris: list[str]
    shape_graph_iris: list[str] = field(default_factory=list)
    governance_graph_iris: list[str] = field(default_factory=list)
    reasoning_result_graph_iri: str | None = None
    derived_state: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, str]] = field(default_factory=list)


class SemanticReadScopeResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(
        self, ontology_id: str, include: str = "asserted", allow_stale_derived: bool = True
    ) -> ScopeResolution:
        if include not in {"asserted", "full-working-view"}:
            raise ReadScopeError(f"Unsupported include value: {include}")
        ontology = self.session.scalar(
            select(OntologyModel).where(OntologyModel.id == ontology_id)
            .execution_options(populate_existing=True)
        )
        if ontology is None or not ontology.model_graph_iri:
            raise ReadScopeError(f"Ontology model is not ready: {ontology_id}")
        fence = self.session.get(OntologyWriteFenceModel, ontology_id)
        if fence is not None:
            raise ReadScopeError(
                f"Ontology model write is pending: {ontology_id}; reconcile attempt {fence.attempt_id} "
                "and retry the read"
            )
        return ScopeResolution(
            ontology_id=ontology_id,
            model_revision=ontology.model_revision,
            include=include,
            model_graph_iris=[ontology.model_graph_iri],
        )
