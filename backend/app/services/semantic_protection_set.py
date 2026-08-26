"""Protection Set management service (R3.0-004).

Shared by the HTTP routes and the MCP tools so both surfaces exercise one
code path. Protection sets are a PostgreSQL control-plane object: a named set
of resource IRIs plus ``allowed_grants`` (OR semantics), owned by a Project.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.models import (
    OntologyModel,
    SemanticProtectionSetMemberModel,
    SemanticProtectionSetModel,
)

_MAX_GRANTS = 64
_MAX_GRANT_LENGTH = 128
_MAX_MEMBERS_PER_CALL = 5000


class ProtectionSetError(Exception):
    """Management-plane error carrying an HTTP status and stable code."""

    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def normalize_grants(grants: list[str] | None) -> list[str]:
    if grants is None:
        return []
    if len(grants) > _MAX_GRANTS:
        raise ProtectionSetError(
            "allowed_grants supports at most 64 items", status_code=422, code="invalid_grants"
        )
    normalized: list[str] = []
    for item in grants:
        if (
            not isinstance(item, str)
            or not item.strip()
            or len(item) > _MAX_GRANT_LENGTH
            or not item.isprintable()
        ):
            raise ProtectionSetError(
                "allowed_grants items must be non-empty printable strings of at most 128 characters",
                status_code=422,
                code="invalid_grants",
            )
        if item not in normalized:
            normalized.append(item)
    return normalized


class SemanticProtectionSetService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _require_set(self, protection_set_id: str) -> SemanticProtectionSetModel:
        record = self._session.get(SemanticProtectionSetModel, protection_set_id)
        if record is None:
            raise ProtectionSetError(
                "Protection set not found", status_code=404, code="protection_set_not_found"
            )
        return record

    def _member_count(self, protection_set_id: str) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(SemanticProtectionSetMemberModel)
                .where(
                    SemanticProtectionSetMemberModel.protection_set_id == protection_set_id
                )
            )
            or 0
        )

    def _set_dict(self, record: SemanticProtectionSetModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "project_id": record.project_id,
            "name": record.name,
            "description": record.description,
            "allowed_grants": list(record.allowed_grants or []),
            "member_count": self._member_count(record.id),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _member_dict(row: SemanticProtectionSetMemberModel) -> dict[str, Any]:
        return {
            "resource_iri": row.resource_iri,
            "ontology_id": row.ontology_id,
            "created_at": row.created_at,
        }

    def list_sets(self, project_id: str) -> list[dict[str, Any]]:
        records = self._session.scalars(
            select(SemanticProtectionSetModel)
            .where(SemanticProtectionSetModel.project_id == project_id)
            .order_by(SemanticProtectionSetModel.created_at)
        ).all()
        return [self._set_dict(record) for record in records]

    def create_set(
        self,
        *,
        project_id: str,
        name: str,
        description: str | None = None,
        allowed_grants: list[str] | None = None,
        members: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_name = (name or "").strip()
        if not normalized_name or len(normalized_name) > 200:
            raise ProtectionSetError(
                "name must be a non-empty string of at most 200 characters",
                status_code=422,
                code="invalid_name",
            )
        grants = normalize_grants(allowed_grants)
        duplicate = self._session.scalar(
            select(SemanticProtectionSetModel).where(
                SemanticProtectionSetModel.project_id == project_id,
                SemanticProtectionSetModel.name == normalized_name,
            )
        )
        if duplicate is not None:
            raise ProtectionSetError(
                "Protection set name already exists in this project",
                status_code=409,
                code="protection_set_name_conflict",
            )
        record = SemanticProtectionSetModel(
            id=str(uuid4()),
            project_id=project_id,
            name=normalized_name,
            description=description,
            allowed_grants=grants,
        )
        self._session.add(record)
        self._session.flush()
        added = self._add_member_rows(record.id, members or [])
        self._session.commit()
        self._session.refresh(record)
        result = self._set_dict(record)
        result["members_added"] = added
        return result

    def get_set(
        self,
        protection_set_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        record = self._require_set(protection_set_id)
        total = self._member_count(record.id)
        rows = self._session.scalars(
            select(SemanticProtectionSetMemberModel)
            .where(
                SemanticProtectionSetMemberModel.protection_set_id == protection_set_id
            )
            .order_by(SemanticProtectionSetMemberModel.created_at)
            .offset(offset)
            .limit(limit)
        ).all()
        result = self._set_dict(record)
        result["members"] = [self._member_dict(row) for row in rows]
        result["member_total"] = total
        result["member_offset"] = offset
        result["member_limit"] = limit
        return result

    def update_set(
        self,
        protection_set_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        allowed_grants: list[str] | None = None,
    ) -> dict[str, Any]:
        record = self._require_set(protection_set_id)
        if name is not None:
            normalized_name = name.strip()
            if not normalized_name or len(normalized_name) > 200:
                raise ProtectionSetError(
                    "name must be a non-empty string of at most 200 characters",
                    status_code=422,
                    code="invalid_name",
                )
            duplicate = self._session.scalar(
                select(SemanticProtectionSetModel).where(
                    SemanticProtectionSetModel.project_id == record.project_id,
                    SemanticProtectionSetModel.name == normalized_name,
                    SemanticProtectionSetModel.id != record.id,
                )
            )
            if duplicate is not None:
                raise ProtectionSetError(
                    "Protection set name already exists in this project",
                    status_code=409,
                    code="protection_set_name_conflict",
                )
            record.name = normalized_name
        if description is not None:
            record.description = description
        if allowed_grants is not None:
            record.allowed_grants = normalize_grants(allowed_grants)
        self._session.commit()
        self._session.refresh(record)
        return self._set_dict(record)

    def delete_set(self, protection_set_id: str) -> None:
        record = self._require_set(protection_set_id)
        if self._member_count(protection_set_id) > 0:
            raise ProtectionSetError(
                "Protection set still has members; remove them before deletion",
                status_code=409,
                code="protection_set_not_empty",
            )
        self._session.delete(record)
        self._session.commit()

    def _add_member_rows(
        self, protection_set_id: str, members: list[dict[str, Any]]
    ) -> int:
        if not members:
            return 0
        if len(members) > _MAX_MEMBERS_PER_CALL:
            raise ProtectionSetError(
                f"at most {_MAX_MEMBERS_PER_CALL} members per call",
                status_code=422,
                code="invalid_members",
            )
        existing = set(
            self._session.scalars(
                select(SemanticProtectionSetMemberModel.resource_iri).where(
                    SemanticProtectionSetMemberModel.protection_set_id
                    == protection_set_id
                )
            ).all()
        )
        seen: set[str] = set()
        added = 0
        for member in members:
            if not isinstance(member, dict):
                raise ProtectionSetError(
                    "members must be objects with resource_iri",
                    status_code=422,
                    code="invalid_members",
                )
            resource_iri = member.get("resource_iri")
            if (
                not isinstance(resource_iri, str)
                or not resource_iri.strip()
                or len(resource_iri) > 1024
            ):
                raise ProtectionSetError(
                    "resource_iri must be a non-empty string of at most 1024 characters",
                    status_code=422,
                    code="invalid_members",
                )
            resource_iri = resource_iri.strip()
            if resource_iri in existing or resource_iri in seen:
                continue
            ontology_id = member.get("ontology_id")
            if ontology_id is not None:
                if not isinstance(ontology_id, str) or not ontology_id.strip():
                    raise ProtectionSetError(
                        "ontology_id must be a non-empty string when provided",
                        status_code=422,
                        code="invalid_members",
                    )
                ontology = self._session.get(OntologyModel, ontology_id)
                if ontology is not None and ontology.project_id is not None:
                    set_record = self._session.get(
                        SemanticProtectionSetModel, protection_set_id
                    )
                    if ontology.project_id != set_record.project_id:
                        raise ProtectionSetError(
                            "ontology_id belongs to a different project",
                            status_code=422,
                            code="invalid_members",
                        )
            self._session.add(
                SemanticProtectionSetMemberModel(
                    protection_set_id=protection_set_id,
                    resource_iri=resource_iri,
                    ontology_id=ontology_id,
                )
            )
            seen.add(resource_iri)
            added += 1
        return added

    def add_members(
        self, protection_set_id: str, members: list[dict[str, Any]]
    ) -> dict[str, Any]:
        record = self._require_set(protection_set_id)
        added = self._add_member_rows(protection_set_id, members)
        self._session.commit()
        self._session.refresh(record)
        return {
            "id": record.id,
            "member_count": self._member_count(record.id),
            "members_added": added,
        }

    def remove_members(
        self, protection_set_id: str, resource_iris: list[str]
    ) -> dict[str, Any]:
        record = self._require_set(protection_set_id)
        removed = 0
        for resource_iri in resource_iris:
            row = self._session.get(
                SemanticProtectionSetMemberModel,
                {"protection_set_id": protection_set_id, "resource_iri": resource_iri},
            )
            if row is not None:
                self._session.delete(row)
                removed += 1
        self._session.commit()
        self._session.refresh(record)
        return {
            "id": record.id,
            "member_count": self._member_count(record.id),
            "members_removed": removed,
        }
