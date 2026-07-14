"""Lightweight project evidence references and modeling-result associations."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.repositories.models import (
    EvidenceAssociationModel,
    EvidenceReferenceModel,
    OntologyModel,
    ProjectModel,
    SemanticEditAuditModel,
    SemanticGraphSetModel,
)


class EvidenceReferenceError(RuntimeError):
    status_code = 400


class EvidenceReferenceNotFound(EvidenceReferenceError):
    status_code = 404


class EvidenceReferenceValidationError(EvidenceReferenceError):
    status_code = 422


@dataclass(frozen=True)
class NormalizedEvidence:
    document_name: str
    excerpt: str
    excerpt_hash: str

    @property
    def idempotency_key(self) -> str:
        return f"{self.document_name}:{self.excerpt_hash}"


def normalize_evidence(document_name: str, excerpt: str) -> NormalizedEvidence:
    normalized_name = document_name.strip()
    normalized_excerpt = excerpt.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_name:
        raise EvidenceReferenceValidationError("document_name must not be blank")
    if not normalized_excerpt:
        raise EvidenceReferenceValidationError("excerpt must not be blank")
    if len(normalized_name) > 255:
        raise EvidenceReferenceValidationError("document_name must be at most 255 characters")
    digest = sha256(normalized_excerpt.encode("utf-8")).hexdigest()
    return NormalizedEvidence(normalized_name, normalized_excerpt, digest)


class EvidenceReferenceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_project(self, project_id: str) -> ProjectModel:
        project = self.session.get(ProjectModel, project_id)
        if project is None:
            raise EvidenceReferenceNotFound(f"Project not found: {project_id}")
        return project

    def prepare(self, document_name: str, excerpt: str) -> NormalizedEvidence:
        return normalize_evidence(document_name, excerpt)

    def find_existing(
        self, project_id: str, normalized: NormalizedEvidence
    ) -> EvidenceReferenceModel | None:
        return self.session.scalar(
            select(EvidenceReferenceModel).where(
                EvidenceReferenceModel.project_id == project_id,
                EvidenceReferenceModel.normalized_document_name == normalized.document_name,
                EvidenceReferenceModel.excerpt_hash == normalized.excerpt_hash,
            )
        )

    def get_or_create(
        self,
        project_id: str,
        document_name: str,
        excerpt: str,
        *,
        actor: str | None = None,
    ) -> tuple[EvidenceReferenceModel, bool]:
        self.require_project(project_id)
        normalized = self.prepare(document_name, excerpt)
        existing = self.find_existing(project_id, normalized)
        if existing is not None:
            return existing, False
        row = EvidenceReferenceModel(
            id=str(uuid4()),
            project_id=project_id,
            document_name=normalized.document_name,
            normalized_document_name=normalized.document_name,
            excerpt=normalized.excerpt,
            excerpt_hash=normalized.excerpt_hash,
            created_by=actor,
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def get(self, reference_id: str, *, project_id: str | None = None) -> EvidenceReferenceModel:
        row = self.session.get(EvidenceReferenceModel, reference_id)
        if row is None or (project_id is not None and row.project_id != project_id):
            raise EvidenceReferenceNotFound("Evidence reference not found")
        return row

    def list_references(
        self,
        project_id: str,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EvidenceReferenceModel], int]:
        self.require_project(project_id)
        filters = [EvidenceReferenceModel.project_id == project_id]
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    EvidenceReferenceModel.document_name.ilike(pattern),
                    EvidenceReferenceModel.excerpt.ilike(pattern),
                )
            )
        statement = (
            select(EvidenceReferenceModel)
            .where(*filters)
            .order_by(EvidenceReferenceModel.created_at.desc(), EvidenceReferenceModel.id)
            .offset(offset)
            .limit(limit)
        )
        total = self.session.scalar(
            select(func.count(EvidenceReferenceModel.id)).where(*filters)
        ) or 0
        return list(self.session.scalars(statement)), int(total)

    def require_ontology_scope(
        self, project_id: str, ontology_id: str, graph_set_id: str | None
    ) -> OntologyModel:
        ontology = self.session.get(OntologyModel, ontology_id)
        if ontology is None or ontology.project_id != project_id:
            raise EvidenceReferenceNotFound("Ontology not found in project")
        if graph_set_id:
            graph_set = self.session.get(SemanticGraphSetModel, graph_set_id)
            if (
                graph_set is None
                or graph_set.scope_type != "ontology"
                or graph_set.scope_id != ontology_id
            ):
                raise EvidenceReferenceNotFound("Graph set not found for ontology")
        return ontology

    def resolve_candidates(
        self,
        project_id: str,
        *,
        reference_ids: list[str] | None = None,
        inline_evidence: list[dict[str, str]] | None = None,
        actor: str | None = None,
        persist: bool = True,
    ) -> list[tuple[EvidenceReferenceModel | None, NormalizedEvidence | None, bool]]:
        self.require_project(project_id)
        resolved: list[tuple[EvidenceReferenceModel | None, NormalizedEvidence | None, bool]] = []
        seen_ids: set[str] = set()
        for reference_id in reference_ids or []:
            row = self.get(reference_id, project_id=project_id)
            if row.id not in seen_ids:
                resolved.append((row, None, False))
                seen_ids.add(row.id)
        for item in inline_evidence or []:
            normalized = self.prepare(item.get("document_name", ""), item.get("excerpt", ""))
            existing = self.find_existing(project_id, normalized)
            if existing is not None:
                if existing.id not in seen_ids:
                    resolved.append((existing, normalized, False))
                    seen_ids.add(existing.id)
                continue
            if persist:
                row, created = self.get_or_create(
                    project_id,
                    normalized.document_name,
                    normalized.excerpt,
                    actor=actor,
                )
                if row.id not in seen_ids:
                    resolved.append((row, normalized, created))
                    seen_ids.add(row.id)
            else:
                key = normalized.idempotency_key
                if key not in seen_ids:
                    resolved.append((None, normalized, True))
                    seen_ids.add(key)
        return resolved

    def associate(
        self,
        *,
        project_id: str,
        ontology_id: str,
        target_type: str,
        target_id: str,
        references: list[EvidenceReferenceModel],
        graph_set_id: str | None = None,
        client_item_id: str | None = None,
        edit_audit_id: str | None = None,
        actor: str | None = None,
    ) -> list[EvidenceAssociationModel]:
        self.require_ontology_scope(project_id, ontology_id, graph_set_id)
        clean_type = target_type.strip()
        clean_target = target_id.strip()
        if not clean_type or not clean_target:
            raise EvidenceReferenceValidationError("target_type and target_id are required")
        if edit_audit_id and self.session.get(SemanticEditAuditModel, edit_audit_id) is None:
            raise EvidenceReferenceNotFound("Semantic edit audit not found")
        rows: list[EvidenceAssociationModel] = []
        for reference in references:
            if reference.project_id != project_id:
                raise EvidenceReferenceNotFound("Evidence reference not found")
            existing = self.session.scalar(
                select(EvidenceAssociationModel).where(
                    EvidenceAssociationModel.ontology_id == ontology_id,
                    EvidenceAssociationModel.target_type == clean_type,
                    EvidenceAssociationModel.target_id == clean_target,
                    EvidenceAssociationModel.evidence_reference_id == reference.id,
                )
            )
            if existing is not None:
                rows.append(existing)
                continue
            association = EvidenceAssociationModel(
                id=str(uuid4()),
                project_id=project_id,
                ontology_id=ontology_id,
                graph_set_id=graph_set_id,
                evidence_reference_id=reference.id,
                target_type=clean_type,
                target_id=clean_target,
                client_item_id=client_item_id,
                edit_audit_id=edit_audit_id,
                created_by=actor,
            )
            self.session.add(association)
            rows.append(association)
        self.session.flush()
        return rows

    def list_associations(
        self,
        *,
        reference_id: str | None = None,
        ontology_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> list[EvidenceAssociationModel]:
        filters = []
        if reference_id:
            filters.append(EvidenceAssociationModel.evidence_reference_id == reference_id)
        if ontology_id:
            filters.append(EvidenceAssociationModel.ontology_id == ontology_id)
        if target_type:
            filters.append(EvidenceAssociationModel.target_type == target_type)
        if target_id:
            filters.append(EvidenceAssociationModel.target_id == target_id)
        return list(
            self.session.scalars(
                select(EvidenceAssociationModel)
                .where(*filters)
                .order_by(EvidenceAssociationModel.created_at.desc())
            )
        )


def reference_to_dict(
    row: EvidenceReferenceModel, *, association_count: int | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "project_id": row.project_id,
        "document_name": row.document_name,
        "excerpt": row.excerpt,
        "excerpt_hash": row.excerpt_hash,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if association_count is not None:
        payload["association_count"] = association_count
    return payload


def association_to_dict(row: EvidenceAssociationModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "ontology_id": row.ontology_id,
        "graph_set_id": row.graph_set_id,
        "evidence_reference_id": row.evidence_reference_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "client_item_id": row.client_item_id,
        "edit_audit_id": row.edit_audit_id,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
