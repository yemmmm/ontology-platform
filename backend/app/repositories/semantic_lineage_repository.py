"""PostgreSQL repository for immutable semantic statement lineage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import (
    SemanticStatementOccurrenceModel,
    SemanticStatementOriginModel,
    SemanticStatementPremiseModel,
)
from app.services.semantic_lineage_identity import occurrence_id_for, statement_id_for_quad


class SemanticLineageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_occurrence(self, occurrence_id: str) -> SemanticStatementOccurrenceModel | None:
        return self.session.get(SemanticStatementOccurrenceModel, occurrence_id)

    def get_or_create_occurrence(
        self,
        *,
        ontology_id: str,
        graph_set_id: str | None,
        subject: str,
        predicate: str,
        object_ntriples: str,
        graph_iri: str,
        graph_revision: int,
        assertion_kind: str,
    ) -> tuple[SemanticStatementOccurrenceModel, bool]:
        statement_id = statement_id_for_quad(subject, predicate, object_ntriples, graph_iri)
        occurrence_id = occurrence_id_for(statement_id, graph_revision)
        existing = self.session.get(SemanticStatementOccurrenceModel, occurrence_id)
        if existing is not None:
            if existing.ontology_id != ontology_id:
                raise ValueError("Statement occurrence belongs to another Ontology")
            return existing, False
        occurrence = SemanticStatementOccurrenceModel(
            id=occurrence_id,
            ontology_id=ontology_id,
            graph_set_id=graph_set_id,
            statement_id=statement_id,
            subject_iri=subject,
            predicate_iri=predicate,
            object_ntriples=object_ntriples,
            graph_iri=graph_iri,
            graph_revision=graph_revision,
            assertion_kind=assertion_kind,
            status="active",
        )
        self.session.add(occurrence)
        self.session.flush()
        return occurrence, True

    def add_origin(
        self,
        occurrence_id: str,
        origin_kind: str,
        origin_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticStatementOriginModel:
        existing = self.session.scalar(
            select(SemanticStatementOriginModel).where(
                SemanticStatementOriginModel.statement_occurrence_id == occurrence_id,
                SemanticStatementOriginModel.origin_kind == origin_kind,
                SemanticStatementOriginModel.origin_id == origin_id,
            )
        )
        if existing is not None:
            existing.origin_metadata = self._merge_origin_metadata(
                existing.origin_metadata or {}, metadata or {}
            )
            self.session.flush()
            return existing
        origin = SemanticStatementOriginModel(
            id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"semantic-lineage-origin:{occurrence_id}:{origin_kind}:{origin_id}",
                )
            ),
            statement_occurrence_id=occurrence_id,
            origin_kind=origin_kind,
            origin_id=origin_id,
            origin_metadata=metadata or {},
        )
        self.session.add(origin)
        self.session.flush()
        return origin

    @staticmethod
    def _merge_origin_metadata(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {**current, **incoming}
        sources: dict[tuple[str, str], dict[str, Any]] = {}
        for source in [
            *(current.get("rule_sources") or []),
            *(incoming.get("rule_sources") or []),
        ]:
            key = (
                str(source.get("rule_definition_id") or ""),
                str(source.get("rule_version") or ""),
            )
            sources[key] = source
        if sources:
            merged["rule_sources"] = [sources[key] for key in sorted(sources)]
        proof_levels = {
            value for value in (current.get("proof_level"), incoming.get("proof_level")) if value
        }
        if "exact" in proof_levels:
            merged["proof_level"] = "exact"
            merged["coarse_reason"] = None
        return merged

    def add_premise(
        self,
        derived_occurrence_id: str,
        premise_occurrence_id: str,
    ) -> SemanticStatementPremiseModel:
        key = (derived_occurrence_id, premise_occurrence_id)
        existing = self.session.get(SemanticStatementPremiseModel, key)
        if existing is not None:
            return existing
        edge = SemanticStatementPremiseModel(
            derived_occurrence_id=derived_occurrence_id,
            premise_occurrence_id=premise_occurrence_id,
            proof_kind="exact",
        )
        self.session.add(edge)
        self.session.flush()
        return edge

    def active_for_statement(
        self, ontology_id: str, statement_id: str
    ) -> list[SemanticStatementOccurrenceModel]:
        return list(
            self.session.scalars(
                select(SemanticStatementOccurrenceModel).where(
                    SemanticStatementOccurrenceModel.ontology_id == ontology_id,
                    SemanticStatementOccurrenceModel.statement_id == statement_id,
                    SemanticStatementOccurrenceModel.status == "active",
                )
            )
        )

    def invalidate(
        self,
        occurrence: SemanticStatementOccurrenceModel,
        *,
        invalidated_revision: int,
        audit_id: str | None,
    ) -> None:
        if occurrence.status == "invalidated":
            return
        occurrence.status = "invalidated"
        occurrence.invalidated_revision = invalidated_revision
        occurrence.invalidated_by_audit_id = audit_id
        occurrence.invalidated_at = datetime.now(UTC)

    def list_occurrences(
        self,
        *,
        ontology_id: str,
        statement_id: str | None = None,
        subject_iri: str | None = None,
        include_history: bool = False,
        limit: int = 200,
    ) -> list[SemanticStatementOccurrenceModel]:
        statement = select(SemanticStatementOccurrenceModel).where(
            SemanticStatementOccurrenceModel.ontology_id == ontology_id
        )
        if statement_id is not None:
            statement = statement.where(
                SemanticStatementOccurrenceModel.statement_id == statement_id
            )
        if subject_iri is not None:
            statement = statement.where(SemanticStatementOccurrenceModel.subject_iri == subject_iri)
        if not include_history:
            statement = statement.where(SemanticStatementOccurrenceModel.status == "active")
        statement = statement.order_by(
            SemanticStatementOccurrenceModel.created_at.desc(),
            SemanticStatementOccurrenceModel.id,
        ).limit(limit)
        return list(self.session.scalars(statement))

    def origins_for(self, occurrence_id: str) -> list[SemanticStatementOriginModel]:
        return list(
            self.session.scalars(
                select(SemanticStatementOriginModel)
                .where(SemanticStatementOriginModel.statement_occurrence_id == occurrence_id)
                .order_by(
                    SemanticStatementOriginModel.origin_kind,
                    SemanticStatementOriginModel.origin_id,
                )
            )
        )

    def premise_ids_for(self, occurrence_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(SemanticStatementPremiseModel.premise_occurrence_id)
                .where(SemanticStatementPremiseModel.derived_occurrence_id == occurrence_id)
                .order_by(SemanticStatementPremiseModel.premise_occurrence_id)
            )
        )
