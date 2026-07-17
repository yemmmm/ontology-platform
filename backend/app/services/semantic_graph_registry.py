"""Graph registry: classification, registration, and direct-edit policy."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticEditAuditModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
    SemanticGraphStateModel,
)


class GraphCategory(StrEnum):
    ONTOLOGY = "ontology"
    DATA = "data"
    SHAPES = "shapes"
    PROPOSAL = "proposal"
    EVIDENCE = "evidence"
    POLICY = "policy"
    IMPORT = "import"
    VALIDATION_RUN = "validation_run"
    REASONING_RUN = "reasoning_run"
    REASONING_RESULT = "reasoning_result"
    RULE_RUN = "rule_run"
    RULE_RESULT = "rule_result"
    REVIEW = "review"
    UNKNOWN = "unknown"


DIRECT_EDITABLE_CATEGORIES: frozenset[GraphCategory] = frozenset(
    {GraphCategory.ONTOLOGY, GraphCategory.DATA, GraphCategory.SHAPES}
)

DERIVED_RESULT_CATEGORIES: frozenset[GraphCategory] = frozenset(
    {GraphCategory.REASONING_RESULT, GraphCategory.RULE_RESULT}
)

RUN_CATEGORIES: frozenset[GraphCategory] = frozenset(
    {
        GraphCategory.VALIDATION_RUN,
        GraphCategory.REASONING_RUN,
        GraphCategory.RULE_RUN,
    }
)


class GraphRegistryError(RuntimeError):
    status_code = 400


class UnmanagedGraphIri(GraphRegistryError):
    pass


class DirectEditCategoryDenied(GraphRegistryError):
    status_code = 409


class GraphClassification:
    """Classify a graph IRI into a canonical Phase 4 category."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def classify(self, graph_iri: str) -> GraphCategory:
        if not graph_iri.startswith(self.prefix):
            return GraphCategory.UNKNOWN
        suffix = graph_iri[len(self.prefix) :]
        head = suffix.split("/", 1)[0]
        normalized = head.replace("-", "_").lower()
        try:
            return GraphCategory(normalized)
        except ValueError:
            return GraphCategory.UNKNOWN


def _owner_metadata(graph_iri: str, category: GraphCategory) -> dict[str, Any]:
    suffix = graph_iri.split("/")[-1] if "/" in graph_iri else ""
    return {"suffix": suffix, "category": category.value}


class SemanticGraphRegistryService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.classifier = GraphClassification(settings.semantic_graph_iri_prefix)

    def classify(self, graph_iri: str) -> GraphCategory:
        return self.classifier.classify(graph_iri)

    def require_managed(self, graph_iri: str) -> None:
        if not graph_iri.startswith(self.settings.semantic_graph_iri_prefix):
            raise UnmanagedGraphIri(
                f"Graph IRI is outside the managed semantic graph prefix: {graph_iri}"
            )

    def require_direct_editable_category(self, graph_iri: str) -> GraphCategory:
        self.require_managed(graph_iri)
        category = self.classify(graph_iri)
        if category not in DIRECT_EDITABLE_CATEGORIES:
            raise DirectEditCategoryDenied(
                f"Direct semantic edits are not allowed for graph category '{category.value}'"
            )
        return category

    def get(self, graph_iri: str) -> SemanticGraphRegistryModel | None:
        return self.session.scalar(
            select(SemanticGraphRegistryModel).where(
                SemanticGraphRegistryModel.graph_iri == graph_iri
            )
        )

    def list_graphs(
        self,
        category: str | None = None,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> list[SemanticGraphRegistryModel]:
        statement = select(SemanticGraphRegistryModel).order_by(
            SemanticGraphRegistryModel.category,
            SemanticGraphRegistryModel.graph_iri,
        )
        if category:
            statement = statement.where(SemanticGraphRegistryModel.category == category)
        if owner_type:
            statement = statement.where(
                SemanticGraphRegistryModel.semantic_owner_type == owner_type
            )
        if owner_id:
            statement = statement.where(SemanticGraphRegistryModel.semantic_owner_id == owner_id)
        return list(self.session.scalars(statement))

    def register_graph(
        self,
        graph_iri: str,
        category: GraphCategory | str | None = None,
        owner_type: str | None = None,
        owner_id: str | None = None,
        created_by: str | None = None,
        mutable_by_direct_edit: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticGraphRegistryModel:
        self.require_managed(graph_iri)
        classified = self.classify(graph_iri) if category is None else _coerce_category(category)
        if classified is GraphCategory.UNKNOWN:
            raise GraphRegistryError(
                f"Unable to classify graph IRI into a Phase 4 category: {graph_iri}"
            )
        if mutable_by_direct_edit is None:
            mutable_by_direct_edit = classified in DIRECT_EDITABLE_CATEGORIES
        record = self.get(graph_iri)
        if record is None:
            record = SemanticGraphRegistryModel(
                id=str(uuid4()),
                graph_iri=graph_iri,
                category=classified.value,
                semantic_owner_type=owner_type,
                semantic_owner_id=owner_id,
                mutable_by_direct_edit=mutable_by_direct_edit,
                managed=True,
                created_by=created_by,
                registry_metadata=metadata or {},
            )
            self.session.add(record)
        else:
            record.category = classified.value
            record.semantic_owner_type = owner_type or record.semantic_owner_type
            record.semantic_owner_id = owner_id or record.semantic_owner_id
            record.mutable_by_direct_edit = (
                mutable_by_direct_edit
                if mutable_by_direct_edit is not None
                else record.mutable_by_direct_edit
            )
            if metadata:
                record.registry_metadata = {**(record.registry_metadata or {}), **metadata}
        self.session.commit()
        return record

    def ensure_registered_for_direct_edit(
        self,
        graph_iri: str,
        actor: str | None = None,
    ) -> SemanticGraphRegistryModel:
        """Auto-register managed ontology/data graphs on direct edit during transition."""
        category = self.require_direct_editable_category(graph_iri)
        record = self.get(graph_iri)
        if record is None:
            record = self.register_graph(
                graph_iri,
                category=category,
                created_by=actor,
                mutable_by_direct_edit=True,
            )
        elif not record.mutable_by_direct_edit:
            raise DirectEditCategoryDenied(f"Graph '{graph_iri}' is not mutable by direct edit")
        return record

    def status_summary(
        self, records: list[SemanticGraphRegistryModel] | None = None
    ) -> dict[str, Any]:
        records = self.list_graphs() if records is None else records
        by_category: dict[str, int] = {}
        editable_actual = 0
        locked_actual = 0
        for record in records:
            by_category[record.category] = by_category.get(record.category, 0) + 1
            if record.category in {c.value for c in DIRECT_EDITABLE_CATEGORIES}:
                state = self._state(record.graph_iri)
                if state is None or state.editable:
                    editable_actual += 1
                else:
                    locked_actual += 1
        return {
            "graph_counts_by_category": by_category,
            "editable_actual_graphs": editable_actual,
            "locked_actual_graphs": locked_actual,
        }

    def graph_status(self, graph_iri: str) -> dict[str, Any]:
        record = self.get(graph_iri)
        if record is None:
            return {
                "graph_iri": graph_iri,
                "category": self.classify(graph_iri).value,
                "registered": False,
                "editable": True,
            }
        state = self._state(graph_iri)
        revision = self._revision(graph_iri)
        derived_pointers = self._derived_pointers(graph_iri)
        return {
            "graph_iri": graph_iri,
            "category": record.category,
            "registered": True,
            "owner_type": record.semantic_owner_type,
            "owner_id": record.semantic_owner_id,
            "mutable_by_direct_edit": record.mutable_by_direct_edit,
            "editable": state.editable if state else True,
            "editability_reason": state.reason if state else None,
            "revision": revision.revision if revision else 0,
            "content_hash": revision.content_hash if revision else None,
            "derived_pointers": derived_pointers,
            "metadata": record.registry_metadata or {},
            "latest_audit_at": self.latest_audit_at(graph_iri),
        }

    def latest_audit_at(self, graph_iri: str) -> datetime | None:
        return self.session.scalar(
            select(func.max(SemanticEditAuditModel.created_at)).where(
                SemanticEditAuditModel.target_graph_iri == graph_iri
            )
        )

    def _state(self, graph_iri: str) -> SemanticGraphStateModel | None:
        return self.session.scalar(
            select(SemanticGraphStateModel).where(SemanticGraphStateModel.graph_iri == graph_iri)
        )

    def _revision(self, graph_iri: str) -> SemanticGraphRevisionModel | None:
        return self.session.scalar(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri == graph_iri
            )
        )

    def _derived_pointers(self, graph_iri: str) -> list[dict[str, Any]]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.result_graph_iri == graph_iri
            )
        )
        return [
            {
                "result_kind": row.result_kind,
                "run_id": row.run_id,
                "graph_set_id": row.graph_set_id,
                "status": row.status,
                "became_current_at": row.became_current_at,
            }
            for row in rows
        ]


def _coerce_category(value: GraphCategory | str) -> GraphCategory:
    if isinstance(value, GraphCategory):
        return value
    try:
        return GraphCategory(value)
    except ValueError as exc:
        raise GraphRegistryError(f"Unknown graph category: {value}") from exc


def graph_set_signature(
    members: list[tuple[str, str, int]],
    revisions_by_graph: dict[str, int],
) -> str:
    """Compute a deterministic signature for a graph set.

    ``members`` is a list of ``(graph_iri, role, sort_order)`` tuples already
    sorted by the caller. ``revisions_by_graph`` provides source-graph revision
    numbers for asserted graphs; missing entries default to 0.
    """
    import hashlib

    parts: list[str] = []
    for graph_iri, role, sort_order in members:
        revision = revisions_by_graph.get(graph_iri, 0)
        parts.append(f"{role}:{graph_iri}:{revision}:{sort_order}")
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def utc_now() -> datetime:
    return datetime.now(UTC)
