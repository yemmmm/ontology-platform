"""Subject-bound semantic knowledge access control (R3.0-004).

One shared authorization code path for HTTP and MCP semantic read surfaces.
``SemanticAccessResolver`` builds a per-request frozen ``SemanticAccessView``
from the caller's ``AuthPrincipal`` and the Project's protection sets; every
semantic surface applies that view before pagination, counting, sorting, or
truncation so wide-scope responses never leak protected members.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories.models import (
    OntologyModel,
    SemanticGraphRegistryModel,
    SemanticGraphSetModel,
)
from app.repositories.models import SemanticProtectionSetMemberModel
from app.repositories.models import SemanticProtectionSetModel
from app.security.auth import AuthPrincipal

logger = logging.getLogger(__name__)


class SemanticAccessDependencyError(RuntimeError):
    """Protection-set control data could not be read; fail closed."""

    status_code = 503
    code = "dependency_error"


@dataclass(frozen=True)
class SemanticAccessView:
    """Frozen per-request view of which semantic members are visible."""

    requires_filtering: bool = False
    _unauthorized_iris: frozenset[str] = frozenset()
    _member_ontology_ids: Mapping[str, str | None] = field(default_factory=dict)

    @classmethod
    def all_visible(cls) -> SemanticAccessView:
        return cls()

    def is_member_visible(self, iri: str | None) -> bool:
        if not self.requires_filtering or not iri:
            return True
        return iri not in self._unauthorized_iris

    def any_unauthorized(self, values: Iterable[Any]) -> bool:
        """True when any of the values names an unauthorized member IRI.

        Used to hide whole result rows (relations, paths, derived rows) that
        reference an unauthorized resource in any projected field.
        """
        if not self.requires_filtering:
            return False
        return any(self._term_unauthorized(value) for value in values)

    def filter_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Drop dict items whose shallow string values reference an
        unauthorized member (covers id/iri plus any projected IRI field)."""
        if not self.requires_filtering:
            return items
        return [
            item for item in items if not self.any_unauthorized(item.values())
        ]

    def _term_unauthorized(self, term: Any) -> bool:
        if isinstance(term, str):
            if term in self._unauthorized_iris:
                return True
            if term.startswith("<") and term.endswith(">"):
                return term[1:-1] in self._unauthorized_iris
        return False

    def is_statement_visible(
        self,
        subject: Any,
        predicate: Any,
        objects: Iterable[Any] = (),
    ) -> bool:
        """A statement is hidden when s, p, or any o position names an
        unauthorized protected member (predicate hiding is a conservative
        tightening)."""
        if not self.requires_filtering:
            return True
        if self._term_unauthorized(subject) or self._term_unauthorized(predicate):
            return False
        return not any(self._term_unauthorized(obj) for obj in objects)

    def filter_statement_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        subject_key: str = "subject_iri",
        predicate_key: str = "predicate_iri",
        object_keys: tuple[str, ...] = ("object_value",),
    ) -> list[dict[str, Any]]:
        """Filter statement-shaped rows before any pagination or counting."""
        if not self.requires_filtering:
            return rows
        return [
            row
            for row in rows
            if self.is_statement_visible(
                row.get(subject_key),
                row.get(predicate_key),
                tuple(row.get(key) for key in object_keys if row.get(key) is not None),
            )
        ]

    def filter_candidate(self, item: Mapping[str, Any]) -> bool:
        """Visibility test for context-query candidate dicts (id/iri plus
        statement positions and shallow mapping-evidence references)."""
        if not self.requires_filtering:
            return True
        for key in ("id", "iri"):
            value = item.get(key)
            if isinstance(value, str) and value in self._unauthorized_iris:
                return False
        data = item.get("data")
        if isinstance(data, Mapping):
            if not self.is_statement_visible(
                data.get("subject"),
                data.get("predicate"),
                [data.get("object")],
            ):
                return False
        evidence = item.get("mapping_evidence")
        if isinstance(evidence, list):
            for record in evidence:
                if isinstance(record, Mapping):
                    for value in record.values():
                        if isinstance(value, str) and value in self._unauthorized_iris:
                            return False
                elif isinstance(record, str) and record in self._unauthorized_iris:
                    return False
        return True

    def filter_quads(self, dataset: Any) -> Any:
        """Drop quads whose s/p/o names an unauthorized member; used by export."""
        if not self.requires_filtering:
            return dataset
        for graph in list(dataset.graphs()):
            for triple in list(graph):
                if not self.is_statement_visible(
                    str(triple[0]), str(triple[1]), [str(triple[2])]
                ):
                    graph.remove(triple)
        return dataset

    def scope_unauthorized_members(
        self, in_scope_ontology_ids: Iterable[str | None]
    ) -> frozenset[str]:
        """Unauthorized protected members whose graph could be in scope for a
        SPARQL request. Members with a null or stale ontology_id are
        conservatively treated as in scope."""
        if not self.requires_filtering:
            return frozenset()
        scope_ids = {
            ontology_id
            for ontology_id in in_scope_ontology_ids
            if ontology_id is not None
        }
        return frozenset(
            iri
            for iri, ontology_id in self._member_ontology_ids.items()
            if ontology_id is None or ontology_id in scope_ids
        )


class SemanticAccessResolver:
    """Resolve one ``SemanticAccessView`` per request; no caching."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(
        self, principal: AuthPrincipal | None, project_id: str | None
    ) -> SemanticAccessView:
        if principal is None:
            raise SemanticAccessDependencyError(
                "Semantic access resolution requires an authenticated principal"
            )
        # Org Admin and the Project's own Admin bypass protection sets.
        if principal.is_org_admin:
            return SemanticAccessView.all_visible()
        if (
            "admin" in principal.effective_scopes
            and principal.project_id is not None
            and principal.project_id == project_id
        ):
            return SemanticAccessView.all_visible()
        if project_id is None:
            return SemanticAccessView.all_visible()
        try:
            sets = self._session.scalars(
                select(SemanticProtectionSetModel).where(
                    SemanticProtectionSetModel.project_id == project_id
                )
            ).all()
            if not sets:
                # Fast path: the Project has no protection sets at all.
                return SemanticAccessView.all_visible()
            grants = principal.semantic_grants
            covering_ids = {
                ps.id
                for ps in sets
                if set(ps.allowed_grants or []) & set(grants)
            }
            members = self._session.scalars(
                select(SemanticProtectionSetMemberModel).where(
                    SemanticProtectionSetMemberModel.protection_set_id.in_(
                        [ps.id for ps in sets]
                    )
                )
            ).all()
            if not members:
                return SemanticAccessView.all_visible()
            known_ontology_ids = set(
                self._session.scalars(select(OntologyModel.id)).all()
            )
            unauthorized: set[str] = set()
            covered: set[str] = set()
            member_ontology: dict[str, str | None] = {}
            for member in members:
                member_ontology[member.resource_iri] = (
                    member.ontology_id
                    if member.ontology_id in known_ontology_ids
                    else None
                )
                if member.protection_set_id in covering_ids:
                    # OR semantics: membership in ANY covering set is enough.
                    covered.add(member.resource_iri)
                    unauthorized.discard(member.resource_iri)
                elif member.resource_iri not in covered:
                    unauthorized.add(member.resource_iri)
            if not unauthorized:
                return SemanticAccessView.all_visible()
            return SemanticAccessView(
                requires_filtering=True,
                _unauthorized_iris=frozenset(unauthorized),
                _member_ontology_ids=member_ontology,
            )
        except SQLAlchemyError as exc:
            logger.error("Semantic access resolution failed: %s", exc)
            raise SemanticAccessDependencyError(
                "Semantic protection data is temporarily unavailable"
            ) from exc


def project_id_for_graph_set(session: Session, graph_set_id: str | None) -> str | None:
    """Owning Project for a graph set (ontology-scoped sets only); None when
    the set is unknown or not ontology-scoped."""
    if not graph_set_id:
        return None
    try:
        graph_set = session.get(SemanticGraphSetModel, graph_set_id)
        if graph_set is None or graph_set.scope_type != "ontology" or not graph_set.scope_id:
            return None
        ontology = session.get(OntologyModel, graph_set.scope_id)
        return ontology.project_id if ontology else None
    except SQLAlchemyError as exc:
        logger.error("Graph-set project resolution failed: %s", exc)
        raise SemanticAccessDependencyError(
            "Semantic protection data is temporarily unavailable"
        ) from exc


def project_id_for_graph_iri(session: Session, graph_iri: str | None) -> str | None:
    """Owning Project for one registered graph; None when unowned/unknown."""
    if not graph_iri:
        return None
    try:
        row = session.scalar(
            select(SemanticGraphRegistryModel).where(
                SemanticGraphRegistryModel.graph_iri == graph_iri
            )
        )
        if row is None or row.semantic_owner_type != "ontology" or not row.semantic_owner_id:
            return None
        ontology = session.get(OntologyModel, row.semantic_owner_id)
        return ontology.project_id if ontology else None
    except SQLAlchemyError as exc:
        logger.error("Graph project resolution failed: %s", exc)
        raise SemanticAccessDependencyError(
            "Semantic protection data is temporarily unavailable"
        ) from exc
