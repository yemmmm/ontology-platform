"""Project/Ontology scope resolution shared by Agent-facing semantic queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.services.authorized_scope_discovery import (
    OntologyQueryReadiness,
    OntologyQueryReadinessEvaluator,
)


class SemanticQueryScopeError(RuntimeError):
    status_code = 400
    code = "invalid_scope"


class SemanticQueryScopeNotFound(SemanticQueryScopeError):
    status_code = 404
    code = "scope_not_found"


class SemanticQueryScopeNotReady(SemanticQueryScopeError):
    status_code = 409
    code = "scope_not_ready"


@dataclass(frozen=True)
class ResolvedOntologyScope:
    ontology_id: str
    ontology_name: str
    graph_set_id: str
    workspace_version: str
    source_signature: str
    graph_iris: tuple[str, ...]
    graph_assertion_kinds: dict[str, str]
    derived_state: dict[str, Any]
    warnings: tuple[dict[str, str], ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "ontology_id": self.ontology_id,
            "ontology_name": self.ontology_name,
            "workspace_version": self.workspace_version,
            "source_signature": self.source_signature,
            "derived_state": self.derived_state,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SemanticQueryScope:
    project_id: str
    mode: Literal["project", "ontologies"]
    status: Literal["complete", "partial"]
    ontologies: tuple[ResolvedOntologyScope, ...]
    excluded_ontologies: tuple[dict[str, str], ...] = ()
    warnings: tuple[dict[str, str], ...] = ()
    graph_to_ontology: dict[str, str] = field(default_factory=dict)
    graph_assertion_kinds: dict[str, str] = field(default_factory=dict)

    @property
    def graph_iris(self) -> list[str]:
        return [graph for item in self.ontologies for graph in item.graph_iris]

    def public_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "mode": self.mode,
            "status": self.status,
            "ontologies": [item.public_dict() for item in self.ontologies],
            "excluded_ontologies": list(self.excluded_ontologies),
        }


class SemanticQueryScopeResolver:
    """Resolve public business scope into current internal semantic graphs."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.readiness = OntologyQueryReadinessEvaluator(session, settings)

    def resolve(
        self,
        *,
        project_id: str,
        scope_mode: str,
        ontology_ids: list[str] | None = None,
    ) -> SemanticQueryScope:
        project_id = project_id.strip() if isinstance(project_id, str) else ""
        ids = ontology_ids or []
        if not project_id:
            raise SemanticQueryScopeError("project_id must be non-empty")
        if scope_mode not in {"project", "ontologies"}:
            raise SemanticQueryScopeError("scope_mode must be project or ontologies")
        if scope_mode == "project" and ids:
            raise SemanticQueryScopeError("ontology_ids must be empty for project scope")
        if scope_mode == "ontologies" and not ids:
            raise SemanticQueryScopeError("ontology_ids must not be empty for ontologies scope")
        if len(ids) != len(set(ids)):
            raise SemanticQueryScopeError("ontology_ids must be unique")
        if len(ids) > 50:
            raise SemanticQueryScopeError("ontology_ids may contain at most 50 values")
        if self.session.get(ProjectModel, project_id) is None:
            raise SemanticQueryScopeNotFound("Semantic query scope was not found")

        if scope_mode == "project":
            ontologies = list(
                self.session.scalars(
                    select(OntologyModel)
                    .where(OntologyModel.project_id == project_id)
                    .order_by(OntologyModel.created_at, OntologyModel.id)
                )
            )
        else:
            by_id = {
                row.id: row
                for row in self.session.scalars(
                    select(OntologyModel).where(OntologyModel.id.in_(ids))
                )
            }
            if any(
                ontology_id not in by_id or by_id[ontology_id].project_id != project_id
                for ontology_id in ids
            ):
                raise SemanticQueryScopeNotFound("Semantic query scope was not found")
            ontologies = [by_id[ontology_id] for ontology_id in ids]

        resolved: list[ResolvedOntologyScope] = []
        excluded: list[dict[str, str]] = []
        for ontology in ontologies:
            readiness = self.readiness.evaluate(ontology)
            if not readiness.queryable:
                if scope_mode == "ontologies":
                    raise SemanticQueryScopeNotReady(
                        "One or more selected Ontology workspaces are not ready"
                    )
                excluded.append(
                    {
                        "ontology_id": ontology.id,
                        "ontology_name": ontology.name,
                        "reason": readiness.unavailable_reason or "workspace_not_ready",
                    }
                )
                continue
            resolved.append(self._resolved_ontology(ontology, readiness))

        if not resolved:
            raise SemanticQueryScopeNotReady("Semantic query scope is not ready")

        status: Literal["complete", "partial"] = "partial" if excluded else "complete"
        warnings: list[dict[str, str]] = []
        if excluded:
            warnings.append(
                {
                    "code": "scope_partial",
                    "message": "One or more Ontology workspaces were excluded from project scope.",
                }
            )
            warnings.extend(
                {
                    "code": "ontology_workspace_excluded",
                    "message": f"Ontology {item['ontology_id']} was excluded: {item['reason']}.",
                }
                for item in excluded
            )

        graph_to_ontology = {
            graph: item.ontology_id for item in resolved for graph in item.graph_iris
        }
        graph_assertion_kinds = {
            graph: kind for item in resolved for graph, kind in item.graph_assertion_kinds.items()
        }
        return SemanticQueryScope(
            project_id=project_id,
            mode=scope_mode,
            status=status,
            ontologies=tuple(resolved),
            excluded_ontologies=tuple(excluded),
            warnings=tuple(warnings),
            graph_to_ontology=graph_to_ontology,
            graph_assertion_kinds=graph_assertion_kinds,
        )

    def _resolve_ontology(self, ontology: OntologyModel) -> ResolvedOntologyScope:
        readiness = self.readiness.evaluate(ontology)
        if not readiness.queryable:
            raise SemanticQueryScopeNotReady("Ontology workspace is not ready")
        return self._resolved_ontology(ontology, readiness)

    @staticmethod
    def _resolved_ontology(
        ontology: OntologyModel, readiness: OntologyQueryReadiness
    ) -> ResolvedOntologyScope:
        graph_set_id = readiness.graph_set_id
        read_scope = readiness.read_scope
        workspace_version = readiness.workspace_version
        if not graph_set_id or read_scope is None or not workspace_version:
            raise SemanticQueryScopeNotReady("Ontology workspace is not ready")
        graph_assertion_kinds = {
            graph: "asserted"
            for graph in [*read_scope.source_graph_iris, *read_scope.shape_graph_iris]
        }
        if read_scope.reasoning_result_graph_iri:
            graph_assertion_kinds[read_scope.reasoning_result_graph_iri] = "owl_inferred"
        if read_scope.rule_result_graph_iri:
            graph_assertion_kinds[read_scope.rule_result_graph_iri] = "rule_derived"
        derived_state = {
            kind: {
                "status": value.get("status"),
                "run_id": value.get("run_id"),
            }
            for kind, value in read_scope.derived_state.items()
        }
        return ResolvedOntologyScope(
            ontology_id=ontology.id,
            ontology_name=ontology.name,
            graph_set_id=graph_set_id,
            workspace_version=workspace_version,
            source_signature=read_scope.source_signature,
            graph_iris=tuple(graph_assertion_kinds),
            graph_assertion_kinds=graph_assertion_kinds,
            derived_state=derived_state,
            warnings=readiness.derived_warnings,
        )
