"""Repository for the fact_evidence_bindings table.

Provides CRUD and batch-lookup operations used by the read-model service
to decorate fact rows with their evidence bindings, and by the new
bind/unbind commands to write/delete bindings.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import FactEvidenceBindingModel


class FactEvidenceBindingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        fact_id: str,
        subject_iri: str,
        predicate_iri: str,
        object_value: str,
        graph_iri: str,
        text: str,
        chunk_id: str | None = None,
        evidence_artifact_id: str | None = None,
        evidence_reference_id: str | None = None,
        document_filename: str | None = None,
        sequence: int | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        actor: str | None = None,
        reason: str | None = None,
    ) -> FactEvidenceBindingModel:
        binding = FactEvidenceBindingModel(
            id=str(uuid4()),
            fact_id=fact_id,
            subject_iri=subject_iri,
            predicate_iri=predicate_iri,
            object_value=object_value,
            graph_iri=graph_iri,
            text=text,
            chunk_id=chunk_id,
            evidence_artifact_id=evidence_artifact_id,
            evidence_reference_id=evidence_reference_id,
            document_filename=document_filename,
            sequence=sequence,
            char_start=char_start,
            char_end=char_end,
            actor=actor,
            reason=reason,
        )
        self.session.add(binding)
        self.session.flush()
        return binding

    def delete(self, binding_id: str) -> bool:
        binding = self.session.get(FactEvidenceBindingModel, binding_id)
        if binding is None:
            return False
        self.session.delete(binding)
        self.session.flush()
        return True

    def list_by_fact_id(self, fact_id: str) -> list[FactEvidenceBindingModel]:
        stmt = (
            select(FactEvidenceBindingModel)
            .where(FactEvidenceBindingModel.fact_id == fact_id)
            .order_by(FactEvidenceBindingModel.created_at)
        )
        return list(self.session.scalars(stmt))

    def list_by_fact_ids(
        self, fact_ids: list[str]
    ) -> dict[str, list[FactEvidenceBindingModel]]:
        """Batch-fetch bindings for multiple fact_ids, bucketed by fact_id."""
        if not fact_ids:
            return {}
        stmt = (
            select(FactEvidenceBindingModel)
            .where(FactEvidenceBindingModel.fact_id.in_(fact_ids))
            .order_by(FactEvidenceBindingModel.created_at)
        )
        result: dict[str, list[FactEvidenceBindingModel]] = {}
        for binding in self.session.scalars(stmt):
            result.setdefault(binding.fact_id, []).append(binding)
        return result

    def count_facts_with_bindings(self, fact_ids: list[str]) -> set[str]:
        """Return the subset of fact_ids that have at least one binding.

        Used by the read-model service to derive missing_evidence state.
        """
        if not fact_ids:
            return set()
        stmt = (
            select(FactEvidenceBindingModel.fact_id)
            .where(FactEvidenceBindingModel.fact_id.in_(fact_ids))
            .distinct()
        )
        return set(self.session.scalars(stmt))
