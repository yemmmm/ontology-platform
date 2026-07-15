"""Idempotent write-side recorder for R-005 statement lineage."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import (
    SemanticGraphRegistryModel,
    SemanticGraphSetModel,
    SemanticStatementOccurrenceModel,
    OntologyModel,
)
from app.repositories.rdf_store import RdfGraphDelta
from app.repositories.semantic_lineage_repository import SemanticLineageRepository
from app.services.semantic_lineage_identity import (
    InvalidLineageStatement,
    normalize_quad,
    statement_id_for_quad,
)

Quad = tuple[str, str, str, str]


class SemanticLineageRecorder:
    """Record lineage only after RDF mutation and revision bump have succeeded."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SemanticLineageRepository(session)

    def record_asserted_delta(
        self,
        *,
        delta: RdfGraphDelta,
        graph_revisions: Mapping[str, int],
        audit_id: str,
        ontology_id: str | None = None,
        graph_set_id: str | None = None,
        modeling_item_effects: Mapping[Quad, Iterable[str]] | None = None,
    ) -> list[SemanticStatementOccurrenceModel]:
        effects = self._normalise_effects(modeling_item_effects or {})
        created: list[SemanticStatementOccurrenceModel] = []
        for graph_iri in (*delta.clear_graphs, *delta.drop_graphs):
            scoped_ontology = ontology_id or self.ontology_id_for_graph(graph_iri)
            if not self._ontology_exists(scoped_ontology):
                continue
            revision = int(graph_revisions.get(graph_iri, 0))
            self._invalidate_matching(
                ontology_id=scoped_ontology,
                graph_iri=graph_iri,
                revision=revision,
                audit_id=audit_id,
            )
        for subject, predicate, obj, graph_iri in delta.deletes:
            scoped_ontology = ontology_id or self.ontology_id_for_graph(graph_iri)
            if not self._ontology_exists(scoped_ontology):
                continue
            self._invalidate_matching(
                ontology_id=scoped_ontology,
                graph_iri=graph_iri,
                revision=int(graph_revisions.get(graph_iri, 0)),
                audit_id=audit_id,
                subject=None if subject.startswith("?") else subject,
                predicate=None if predicate.startswith("?") else predicate,
                obj=None if obj.startswith("?") else obj,
            )
        for raw_quad in delta.inserts:
            try:
                subject, predicate, obj, graph_iri = normalize_quad(*raw_quad)
            except InvalidLineageStatement:
                continue
            scoped_ontology = ontology_id or self.ontology_id_for_graph(graph_iri)
            if not self._ontology_exists(scoped_ontology):
                continue
            revision = int(graph_revisions.get(graph_iri, 0))
            occurrence, _was_created = self.repository.get_or_create_occurrence(
                ontology_id=scoped_ontology,
                graph_set_id=graph_set_id,
                subject=subject,
                predicate=predicate,
                object_ntriples=obj,
                graph_iri=graph_iri,
                graph_revision=revision,
                assertion_kind="asserted",
            )
            # Re-inserting the same quad is a new occurrence at the new graph revision.
            for active in self.repository.active_for_statement(
                scoped_ontology, occurrence.statement_id
            ):
                if active.id != occurrence.id:
                    self.repository.invalidate(
                        active,
                        invalidated_revision=revision,
                        audit_id=audit_id,
                    )
            self.repository.add_origin(occurrence.id, "edit_audit", audit_id)
            for item_id in effects.get((subject, predicate, obj, graph_iri), []):
                self.repository.add_origin(occurrence.id, "modeling_item", item_id)
            created.append(occurrence)
        self.session.flush()
        return created

    def record_derived_statements(
        self,
        *,
        ontology_id: str,
        graph_set_id: str | None,
        result_graph_iri: str,
        statements: list[dict[str, Any]],
        assertion_kind: str,
        origin_kind: str,
        run_id: str,
        proof_level: str,
        input_graph_revisions: Mapping[str, int] | None = None,
        premises_by_output: Mapping[int, list[Quad]] | None = None,
        origin_metadata: dict[str, Any] | None = None,
    ) -> list[SemanticStatementOccurrenceModel]:
        input_revisions = input_graph_revisions or {}
        premises_by_output = premises_by_output or {}
        occurrences: list[SemanticStatementOccurrenceModel] = []
        for index, statement in enumerate(statements):
            try:
                subject, predicate, obj, graph_iri = normalize_quad(
                    str(statement["s"]),
                    str(statement["p"]),
                    str(statement["o"]),
                    result_graph_iri,
                )
            except (KeyError, InvalidLineageStatement):
                continue
            item_kind = str(statement.get("assertion_kind") or assertion_kind)
            item_proof_level = str(statement.get("lineage_proof_level") or proof_level)
            item_origin_metadata = {
                **(origin_metadata or {}),
                **(statement.get("lineage_origin_metadata") or {}),
            }
            occurrence, _created = self.repository.get_or_create_occurrence(
                ontology_id=ontology_id,
                graph_set_id=graph_set_id,
                subject=subject,
                predicate=predicate,
                object_ntriples=obj,
                graph_iri=graph_iri,
                graph_revision=1,
                assertion_kind=item_kind,
            )
            self.repository.add_origin(
                occurrence.id,
                origin_kind,
                run_id,
                {"proof_level": item_proof_level, **item_origin_metadata},
            )
            if item_proof_level == "exact":
                statement_premises = statement.get("lineage_premises")
                premise_quads = statement_premises or premises_by_output.get(index, [])
                for premise_quad in premise_quads:
                    premise = self._resolve_or_record_legacy_premise(
                        ontology_id=ontology_id,
                        graph_set_id=graph_set_id,
                        quad=tuple(premise_quad),
                        input_graph_revisions=input_revisions,
                    )
                    if premise is not None and premise.id != occurrence.id:
                        self.repository.add_premise(occurrence.id, premise.id)
            occurrences.append(occurrence)
        self.session.flush()
        return occurrences

    def ontology_id_for_graph(self, graph_iri: str) -> str | None:
        registry = self.session.scalar(
            select(SemanticGraphRegistryModel).where(
                SemanticGraphRegistryModel.graph_iri == graph_iri,
                SemanticGraphRegistryModel.semantic_owner_type == "ontology",
            )
        )
        return registry.semantic_owner_id if registry is not None else None

    def ontology_id_for_graph_set(self, graph_set_id: str) -> str | None:
        graph_set = self.session.get(SemanticGraphSetModel, graph_set_id)
        if graph_set is None or graph_set.scope_type != "ontology":
            return None
        return graph_set.scope_id

    def _ontology_exists(self, ontology_id: str | None) -> bool:
        return bool(ontology_id and self.session.get(OntologyModel, ontology_id) is not None)

    def _invalidate_matching(
        self,
        *,
        ontology_id: str,
        graph_iri: str,
        revision: int,
        audit_id: str,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
    ) -> None:
        statement = select(SemanticStatementOccurrenceModel).where(
            SemanticStatementOccurrenceModel.ontology_id == ontology_id,
            SemanticStatementOccurrenceModel.graph_iri == graph_iri,
            SemanticStatementOccurrenceModel.status == "active",
        )
        try:
            if subject is not None:
                statement = statement.where(
                    SemanticStatementOccurrenceModel.subject_iri
                    == normalize_quad(subject, "urn:lineage:predicate", '"x"', graph_iri)[0]
                )
            if predicate is not None:
                statement = statement.where(
                    SemanticStatementOccurrenceModel.predicate_iri
                    == normalize_quad("urn:lineage:subject", predicate, '"x"', graph_iri)[1]
                )
            if obj is not None:
                statement = statement.where(
                    SemanticStatementOccurrenceModel.object_ntriples
                    == normalize_quad(
                        "urn:lineage:subject", "urn:lineage:predicate", obj, graph_iri
                    )[2]
                )
        except InvalidLineageStatement:
            return
        for occurrence in self.session.scalars(statement):
            self.repository.invalidate(
                occurrence,
                invalidated_revision=revision,
                audit_id=audit_id,
            )

    def _resolve_or_record_legacy_premise(
        self,
        *,
        ontology_id: str,
        graph_set_id: str | None,
        quad: Quad,
        input_graph_revisions: Mapping[str, int],
    ) -> SemanticStatementOccurrenceModel | None:
        try:
            subject, predicate, obj, graph_iri = normalize_quad(*quad)
        except InvalidLineageStatement:
            return None
        statement_id = statement_id_for_quad(subject, predicate, obj, graph_iri)
        active = self.repository.active_for_statement(ontology_id, statement_id)
        if active:
            return max(active, key=lambda row: row.graph_revision)
        revision = int(input_graph_revisions.get(graph_iri, 0))
        occurrence, _created = self.repository.get_or_create_occurrence(
            ontology_id=ontology_id,
            graph_set_id=graph_set_id,
            subject=subject,
            predicate=predicate,
            object_ntriples=obj,
            graph_iri=graph_iri,
            graph_revision=revision,
            assertion_kind="asserted",
        )
        self.repository.add_origin(
            occurrence.id,
            "legacy_unknown",
            f"{graph_iri}:{revision}",
            {"warning": "legacy_lineage_unavailable"},
        )
        return occurrence

    @staticmethod
    def _normalise_effects(
        effects: Mapping[Quad, Iterable[str]],
    ) -> dict[Quad, list[str]]:
        normalized: dict[Quad, list[str]] = {}
        for quad, item_ids in effects.items():
            try:
                key = normalize_quad(*quad)
            except InvalidLineageStatement:
                continue
            normalized[key] = sorted(set(str(item_id) for item_id in item_ids))
        return normalized


__all__ = ["SemanticLineageRecorder"]
