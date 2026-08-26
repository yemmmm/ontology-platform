"""Protection Set management HTTP routes (R3.0-004 §10.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.security.auth import AuthPrincipal, audit_security_event
from app.security.http import principal_dependency
from app.services.semantic_protection_set import (
    ProtectionSetError,
    SemanticProtectionSetService,
)

router = APIRouter(tags=["semantic-protection-sets"])


class ProtectionSetMember(BaseModel):
    resource_iri: str = Field(min_length=1, max_length=1024)
    ontology_id: str | None = None


class ProtectionSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    allowed_grants: list[str] | None = None
    members: list[ProtectionSetMember] | None = None


class ProtectionSetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    allowed_grants: list[str] | None = None


class ProtectionSetMembersAdd(BaseModel):
    members: list[ProtectionSetMember] = Field(min_length=1)


class ProtectionSetMembersRemove(BaseModel):
    resource_iris: list[str] = Field(min_length=1)


class ProtectionSetRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    allowed_grants: list[str]
    member_count: int
    created_at: datetime
    updated_at: datetime


class ProtectionSetDetail(ProtectionSetRead):
    members: list[dict[str, Any]]
    member_total: int
    member_offset: int
    member_limit: int


def _error(exc: ProtectionSetError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code})


@router.get(
    "/projects/{project_id}/protection-sets",
    response_model=list[ProtectionSetRead],
)
def list_protection_sets(
    project_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> list[ProtectionSetRead]:
    try:
        sets = SemanticProtectionSetService(session).list_sets(project_id)
    except ProtectionSetError as exc:
        raise _error(exc) from exc
    return [ProtectionSetRead(**item) for item in sets]


@router.post(
    "/projects/{project_id}/protection-sets",
    response_model=ProtectionSetRead,
    status_code=201,
)
def create_protection_set(
    project_id: str,
    payload: ProtectionSetCreate,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> ProtectionSetRead:
    try:
        service = SemanticProtectionSetService(session)
        item = service.create_set(
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            allowed_grants=payload.allowed_grants,
            members=[member.model_dump() for member in payload.members or []],
        )
    except ProtectionSetError as exc:
        raise _error(exc) from exc
    audit_security_event(
        request.app.state.session_factory,
        "semantic_protection_set_created",
        "success",
        principal,
        project_id=project_id,
        resource_type="semantic_protection_set",
        resource_id=item["id"],
        details={"name": item["name"], "member_count": item["member_count"]},
    )
    item.pop("members_added", None)
    return ProtectionSetRead(**item)


@router.get(
    "/protection-sets/{protection_set_id}",
    response_model=ProtectionSetDetail,
)
def get_protection_set(
    protection_set_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
    limit: int = 100,
    offset: int = 0,
) -> ProtectionSetDetail:
    try:
        item = SemanticProtectionSetService(session).get_set(
            protection_set_id, limit=limit, offset=offset
        )
    except ProtectionSetError as exc:
        raise _error(exc) from exc
    return ProtectionSetDetail(**item)


@router.patch(
    "/protection-sets/{protection_set_id}",
    response_model=ProtectionSetRead,
)
def update_protection_set(
    protection_set_id: str,
    payload: ProtectionSetUpdate,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> ProtectionSetRead:
    try:
        service = SemanticProtectionSetService(session)
        item = service.update_set(
            protection_set_id,
            name=payload.name,
            description=payload.description,
            allowed_grants=payload.allowed_grants,
        )
    except ProtectionSetError as exc:
        raise _error(exc) from exc
    audit_security_event(
        request.app.state.session_factory,
        "semantic_protection_set_updated",
        "success",
        principal,
        project_id=item["project_id"],
        resource_type="semantic_protection_set",
        resource_id=protection_set_id,
        details={
            "name": item["name"],
            "allowed_grants": item["allowed_grants"],
            "member_count": item["member_count"],
        },
    )
    return ProtectionSetRead(**item)


@router.delete("/protection-sets/{protection_set_id}", status_code=204)
def delete_protection_set(
    protection_set_id: str,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> None:
    service = SemanticProtectionSetService(session)
    try:
        item = service.get_set(protection_set_id)
        service.delete_set(protection_set_id)
    except ProtectionSetError as exc:
        raise _error(exc) from exc
    audit_security_event(
        request.app.state.session_factory,
        "semantic_protection_set_deleted",
        "success",
        principal,
        project_id=item["project_id"],
        resource_type="semantic_protection_set",
        resource_id=protection_set_id,
        details={"name": item["name"]},
    )


@router.post(
    "/protection-sets/{protection_set_id}/members",
    response_model=dict[str, Any],
)
def add_protection_set_members(
    protection_set_id: str,
    payload: ProtectionSetMembersAdd,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        service = SemanticProtectionSetService(session)
        result = service.add_members(
            protection_set_id,
            [member.model_dump() for member in payload.members],
        )
        detail = service.get_set(protection_set_id)
    except ProtectionSetError as exc:
        raise _error(exc) from exc
    audit_security_event(
        request.app.state.session_factory,
        "semantic_protection_set_members_added",
        "success",
        principal,
        project_id=detail["project_id"],
        resource_type="semantic_protection_set",
        resource_id=protection_set_id,
        details={
            "name": detail["name"],
            "member_count": result["member_count"],
        },
    )
    return result


@router.delete(
    "/protection-sets/{protection_set_id}/members",
    response_model=dict[str, Any],
)
def remove_protection_set_members(
    protection_set_id: str,
    payload: ProtectionSetMembersRemove,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        service = SemanticProtectionSetService(session)
        result = service.remove_members(protection_set_id, payload.resource_iris)
        detail = service.get_set(protection_set_id)
    except ProtectionSetError as exc:
        raise _error(exc) from exc
    audit_security_event(
        request.app.state.session_factory,
        "semantic_protection_set_members_removed",
        "success",
        principal,
        project_id=detail["project_id"],
        resource_type="semantic_protection_set",
        resource_id=protection_set_id,
        details={
            "name": detail["name"],
            "member_count": result["member_count"],
        },
    )
    return result
