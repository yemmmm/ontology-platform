"""One current business-model graph and version, owned directly by Ontology."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
    SemanticGraphStateModel,
)


class OntologyWorkspaceError(RuntimeError):
    status_code = 409


def model_graph_iri(settings: Settings, ontology_id: str) -> str:
    return f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/{ontology_id}"


class OntologyWorkspaceService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def ensure(self, ontology: OntologyModel, *, dry_run: bool = False) -> dict[str, Any]:
        iri = model_graph_iri(self.settings, ontology.id)
        actions, conflicts = [], []
        if ontology.model_graph_iri not in {None, iri}:
            conflicts.append(
                {"resource": ontology.id, "detail": "Ontology model storage conflicts"}
            )
        if ontology.model_graph_iri is None:
            actions.append({"action": "initialize_model", "resource": ontology.id})
            if not dry_run:
                ontology.model_graph_iri = iri
                ontology.model_revision = 0
                ontology.model_content_hash = hashlib.sha256(b"").hexdigest()
        registry = self.session.scalar(
            select(SemanticGraphRegistryModel).where(SemanticGraphRegistryModel.graph_iri == iri)
        )
        if registry and (registry.semantic_owner_type, registry.semantic_owner_id) != (
            "ontology",
            ontology.id,
        ):
            conflicts.append({"resource": ontology.id, "detail": "Model graph ownership conflicts"})
        elif registry is None:
            actions.append({"action": "initialize_storage", "resource": ontology.id})
            if not dry_run:
                self.session.add(
                    SemanticGraphRegistryModel(
                        id=str(uuid5(NAMESPACE_URL, f"model-registry:{ontology.id}")),
                        graph_iri=iri,
                        category="ontology",
                        semantic_owner_type="ontology",
                        semantic_owner_id=ontology.id,
                        mutable_by_direct_edit=True,
                        managed=True,
                        registry_metadata={},
                    )
                )
        revision = self.session.scalar(
            select(SemanticGraphRevisionModel).where(SemanticGraphRevisionModel.graph_iri == iri)
        )
        if revision is None:
            actions.append({"action": "initialize_revision", "resource": ontology.id})
            if not dry_run:
                self.session.add(
                    SemanticGraphRevisionModel(
                        id=str(uuid5(NAMESPACE_URL, f"model-revision:{ontology.id}")),
                        graph_iri=iri,
                        revision=ontology.model_revision or 0,
                        content_hash=ontology.model_content_hash,
                        revision_metadata={},
                    )
                )
        if conflicts and not dry_run:
            raise OntologyWorkspaceError("; ".join(item["detail"] for item in conflicts))
        if not dry_run:
            self.session.flush()
        return {
            "ontology_id": ontology.id,
            "dry_run": dry_run,
            "actions": actions,
            "conflicts": conflicts,
            "ready": not conflicts and (not dry_run or not actions),
        }

    def context(self, ontology_id: str) -> dict[str, Any]:
        ontology = self.session.scalar(
            select(OntologyModel).where(OntologyModel.id == ontology_id)
            .execution_options(populate_existing=True)
        )
        if ontology is None:
            raise LookupError("Ontology not found")
        iri = ontology.model_graph_iri
        issues = [] if iri else ["model_not_initialized"]
        state = (
            self.session.scalar(
                select(SemanticGraphStateModel).where(SemanticGraphStateModel.graph_iri == iri)
            )
            if iri
            else None
        )
        return {
            "ontology_id": ontology_id,
            "state": "incomplete" if issues else "ready",
            "model_graph_iri": iri,
            "model_revision": ontology.model_revision,
            "content_hash": ontology.model_content_hash,
            "editable": state.editable if state else True,
            "editability_reason": state.reason if state else None,
            "issues": issues,
        }

    def repair(self, ontology_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        ontology = self.session.get(OntologyModel, ontology_id)
        if ontology is None:
            raise LookupError("Ontology not found")
        report = self.ensure(ontology, dry_run=dry_run)
        if not dry_run:
            self.session.commit()
        from app.api.schemas import OntologyWorkspaceContextRead

        report["workspace"] = OntologyWorkspaceContextRead.model_validate(
            self.context(ontology_id)
        ).model_dump()
        return report

    def repair_project(self, project_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        ids = self.session.scalars(
            select(OntologyModel.id).where(OntologyModel.project_id == project_id)
        )
        results = [self.repair(oid, dry_run=dry_run) for oid in ids]
        return {
            "project_id": project_id,
            "dry_run": dry_run,
            "ontology_count": len(results),
            "results": results,
        }
