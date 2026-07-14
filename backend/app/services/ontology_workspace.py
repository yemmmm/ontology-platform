"""Deterministic default semantic workspace lifecycle for an Ontology."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
    SemanticGraphStateModel,
)
from app.services.semantic_graph_registry import graph_set_signature


class OntologyWorkspaceError(RuntimeError):
    status_code = 409


@dataclass(frozen=True)
class DefaultGraphSpec:
    role: str
    category: str
    editable: bool
    sort_order: int


DEFAULT_GRAPH_SPECS = (
    DefaultGraphSpec("asserted_ontology", "ontology", True, 0),
    DefaultGraphSpec("asserted_data", "data", True, 1),
    DefaultGraphSpec("shapes", "shapes", True, 2),
    DefaultGraphSpec("policy", "policy", False, 3),
)


def _stable_id(ontology_id: str, resource: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ontology-platform:{ontology_id}:{resource}"))


def _graph_iri(settings: Settings, ontology_id: str, category: str) -> str:
    return f"{settings.semantic_graph_iri_prefix.rstrip('/')}/{category}/{ontology_id}"


def _default_members(settings: Settings, ontology_id: str) -> list[dict[str, Any]]:
    return [
        {
            "role": spec.role,
            "category": spec.category,
            "editable": spec.editable,
            "sort_order": spec.sort_order,
            "graph_iri": _graph_iri(settings, ontology_id, spec.category),
        }
        for spec in DEFAULT_GRAPH_SPECS
    ]


class OntologyWorkspaceService:
    """Create, inspect, and repair an Ontology's one default workspace.

    The service never commits while ensuring resources. Transaction ownership
    stays with the caller so Ontology creation and initialization are atomic.
    """

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def ensure(self, ontology: OntologyModel, *, dry_run: bool = False) -> dict[str, Any]:
        actions: list[dict[str, str]] = []
        conflicts: list[dict[str, str]] = []
        members = _default_members(self.settings, ontology.id)

        for member in members:
            self._ensure_graph(ontology, member, actions, conflicts, dry_run)
        graph_set = self._ensure_graph_set(ontology, members, actions, conflicts, dry_run)

        if conflicts and not dry_run:
            raise OntologyWorkspaceError(
                "Default semantic workspace conflicts: "
                + "; ".join(item["detail"] for item in conflicts)
            )
        if graph_set is not None and not dry_run:
            self.session.flush()
            revision_rows = self.session.scalars(
                select(SemanticGraphRevisionModel).where(
                    SemanticGraphRevisionModel.graph_iri.in_(
                        [member["graph_iri"] for member in members]
                    )
                )
            )
            revisions = {row.graph_iri: row.revision for row in revision_rows}
            graph_set.source_signature = graph_set_signature(
                [(m["graph_iri"], m["role"], m["sort_order"]) for m in members],
                revisions,
            )
            self.session.flush()

        return {
            "ontology_id": ontology.id,
            "dry_run": dry_run,
            "actions": actions,
            "conflicts": conflicts,
            "ready": not conflicts and (not dry_run or not actions),
        }

    def context(self, ontology_id: str) -> dict[str, Any]:
        ontology = self.session.get(OntologyModel, ontology_id)
        if ontology is None:
            raise LookupError("Ontology not found")

        expected = _default_members(self.settings, ontology_id)
        graph_sets = list(
            self.session.scalars(
                select(SemanticGraphSetModel).where(
                    SemanticGraphSetModel.scope_type == "ontology",
                    SemanticGraphSetModel.scope_id == ontology_id,
                    SemanticGraphSetModel.is_default.is_(True),
                )
            )
        )
        graph_set = graph_sets[0] if len(graph_sets) == 1 else None
        members_by_role: dict[str, list[SemanticGraphSetMemberModel]] = {}
        if graph_set:
            for member in graph_set.members:
                members_by_role.setdefault(member.role, []).append(member)
        actual_members = {role: members[0] for role, members in members_by_role.items()}
        rows: list[dict[str, Any]] = []
        issues: list[str] = []

        if not graph_set:
            issues.append("default_graph_set_missing" if not graph_sets else "multiple_default_graph_sets")
        elif graph_set.status != "active":
            issues.append("default_graph_set_not_active")
        expected_roles = {item["role"] for item in expected}
        for role, members in members_by_role.items():
            if role not in expected_roles:
                issues.append(f"member_unexpected:{role}")
            elif len(members) > 1:
                issues.append(f"member_duplicate:{role}")

        for item in expected:
            registry = self.session.scalar(
                select(SemanticGraphRegistryModel).where(
                    SemanticGraphRegistryModel.graph_iri == item["graph_iri"]
                )
            )
            revision = self.session.scalar(
                select(SemanticGraphRevisionModel).where(
                    SemanticGraphRevisionModel.graph_iri == item["graph_iri"]
                )
            )
            state = self.session.scalar(
                select(SemanticGraphStateModel).where(
                    SemanticGraphStateModel.graph_iri == item["graph_iri"]
                )
            )
            actual = actual_members.get(item["role"])
            if actual is None or actual.graph_iri != item["graph_iri"]:
                issues.append(f"member_invalid:{item['role']}")
            registry_ok = bool(
                registry
                and registry.category == item["category"]
                and registry.semantic_owner_type == "ontology"
                and registry.semantic_owner_id == ontology_id
            )
            if not registry_ok:
                issues.append(f"registry_invalid:{item['role']}")
            if revision is None:
                issues.append(f"revision_missing:{item['role']}")
            editable = state.editable if state is not None else bool(
                registry and registry.mutable_by_direct_edit
            )
            rows.append(
                {
                    "role": item["role"],
                    "graph_iri": item["graph_iri"],
                    "category": item["category"],
                    "required": True,
                    "revision": revision.revision if revision else None,
                    "content_hash": revision.content_hash if revision else None,
                    "editable": editable,
                    "editability_reason": state.reason if state else None,
                    "owner_type": registry.semantic_owner_type if registry else None,
                    "owner_id": registry.semantic_owner_id if registry else None,
                }
            )

        return {
            "ontology_id": ontology_id,
            "state": "ready" if not issues else "incomplete",
            "default_graph_set_id": graph_set.id if graph_set else None,
            "graph_set_status": graph_set.status if graph_set else None,
            "source_signature": graph_set.source_signature if graph_set else None,
            "members": rows,
            "issues": issues,
        }

    def repair(self, ontology_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        ontology = self.session.get(OntologyModel, ontology_id)
        if ontology is None:
            raise LookupError("Ontology not found")
        report = self.ensure(ontology, dry_run=dry_run)
        if not dry_run:
            self.session.commit()
        report["workspace"] = self.context(ontology_id)
        return report

    def repair_project(self, project_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        ontologies = list(
            self.session.scalars(
                select(OntologyModel)
                .where(OntologyModel.project_id == project_id)
                .order_by(OntologyModel.created_at)
            )
        )
        results = [self.repair(ontology.id, dry_run=dry_run) for ontology in ontologies]
        return {
            "project_id": project_id,
            "dry_run": dry_run,
            "ontology_count": len(results),
            "results": results,
        }

    def _ensure_graph(
        self,
        ontology: OntologyModel,
        member: dict[str, Any],
        actions: list[dict[str, str]],
        conflicts: list[dict[str, str]],
        dry_run: bool,
    ) -> None:
        graph_iri = member["graph_iri"]
        registry = self.session.scalar(
            select(SemanticGraphRegistryModel).where(
                SemanticGraphRegistryModel.graph_iri == graph_iri
            )
        )
        if registry is None:
            actions.append({"action": "create_graph_registry", "resource": graph_iri})
            if not dry_run:
                self.session.add(
                    SemanticGraphRegistryModel(
                        id=_stable_id(ontology.id, f"registry:{member['role']}"),
                        graph_iri=graph_iri,
                        category=member["category"],
                        semantic_owner_type="ontology",
                        semantic_owner_id=ontology.id,
                        mutable_by_direct_edit=member["editable"],
                        managed=True,
                        registry_metadata={"workspace_role": member["role"], "default": True},
                    )
                )
        elif (
            registry.category != member["category"]
            or registry.semantic_owner_type not in {None, "ontology"}
            or registry.semantic_owner_id not in {None, ontology.id}
        ):
            conflicts.append(
                {"resource": graph_iri, "detail": f"graph registry ownership/category conflict: {graph_iri}"}
            )
        else:
            if registry.semantic_owner_type is None or registry.semantic_owner_id is None:
                actions.append({"action": "repair_graph_owner", "resource": graph_iri})
                if not dry_run:
                    registry.semantic_owner_type = "ontology"
                    registry.semantic_owner_id = ontology.id
            if registry.mutable_by_direct_edit != member["editable"]:
                actions.append({"action": "repair_edit_policy", "resource": graph_iri})
                if not dry_run:
                    registry.mutable_by_direct_edit = member["editable"]

        revision = self.session.scalar(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri == graph_iri
            )
        )
        if revision is None:
            actions.append({"action": "create_graph_revision", "resource": graph_iri})
            if not dry_run:
                self.session.add(
                    SemanticGraphRevisionModel(
                        id=_stable_id(ontology.id, f"revision:{member['role']}"),
                        graph_iri=graph_iri,
                        revision=0,
                        content_hash=hashlib.sha256(b"").hexdigest(),
                        revision_metadata={"workspace_role": member["role"], "initial": True},
                    )
                )

    def _ensure_graph_set(
        self,
        ontology: OntologyModel,
        members: list[dict[str, Any]],
        actions: list[dict[str, str]],
        conflicts: list[dict[str, str]],
        dry_run: bool,
    ) -> SemanticGraphSetModel | None:
        defaults = list(
            self.session.scalars(
                select(SemanticGraphSetModel).where(
                    SemanticGraphSetModel.scope_type == "ontology",
                    SemanticGraphSetModel.scope_id == ontology.id,
                    SemanticGraphSetModel.is_default.is_(True),
                )
            )
        )
        if len(defaults) > 1:
            conflicts.append({"resource": ontology.id, "detail": "multiple default graph sets exist"})
            return None
        graph_set = defaults[0] if defaults else None
        if graph_set is None:
            actions.append({"action": "create_default_graph_set", "resource": ontology.id})
            if dry_run:
                actions.extend(
                    {"action": "create_graph_set_member", "resource": item["role"]}
                    for item in members
                )
                return None
            graph_set = SemanticGraphSetModel(
                id=_stable_id(ontology.id, "graph-set:default"),
                name="Default workspace",
                scope_type="ontology",
                scope_id=ontology.id,
                status="active",
                is_default=True,
                source_signature="",
                graph_set_metadata={"default": True, "workspace_version": "r001-v1"},
            )
            self.session.add(graph_set)
            self.session.flush()
        elif graph_set.status != "active":
            conflicts.append({"resource": graph_set.id, "detail": "default graph set is not active"})
            return graph_set

        by_role: dict[str, list[SemanticGraphSetMemberModel]] = {}
        for actual in graph_set.members:
            by_role.setdefault(actual.role, []).append(actual)
        expected_roles = {item["role"] for item in members}
        for role, actuals in by_role.items():
            if role not in expected_roles or len(actuals) > 1:
                conflicts.append(
                    {"resource": graph_set.id, "detail": f"unexpected or duplicate graph-set role: {role}"}
                )
        for item in members:
            actuals = by_role.get(item["role"], [])
            if actuals and actuals[0].graph_iri != item["graph_iri"]:
                conflicts.append(
                    {"resource": graph_set.id, "detail": f"graph-set role points to another graph: {item['role']}"}
                )
            elif not actuals:
                actions.append({"action": "create_graph_set_member", "resource": item["role"]})
                if not dry_run:
                    graph_set.members.append(
                        SemanticGraphSetMemberModel(
                            id=_stable_id(ontology.id, f"member:{item['role']}"),
                            graph_iri=item["graph_iri"],
                            role=item["role"],
                            required=True,
                            sort_order=item["sort_order"],
                            member_metadata={"default": True},
                        )
                    )
        return graph_set
