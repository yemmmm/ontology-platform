"""Administrator API for stable users, project membership and semantic permission roles."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.core.config import Settings
from app.repositories.models import (
    ProjectModel,
    ProjectUserMembershipModel,
    SemanticAccessRoleMemberModel,
    SemanticAccessRoleModel,
    UserModel,
)
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.subject_access import (
    business_role_status,
    commit_configuration,
    remove_member,
    replace_roles,
    save_role,
)

router = APIRouter(tags=["subject semantic access"])
Principal = Annotated[AuthPrincipal, Depends(principal_dependency)]
DB = Annotated[Session, Depends(get_db_session)]


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserCreate(StrictPayload):
    username: str = Field(min_length=1, max_length=200)


class UserUpdate(StrictPayload):
    username: str | None = Field(default=None, min_length=1, max_length=200)
    disabled: bool | None = None


class MemberCreate(StrictPayload):
    user_id: str = Field(min_length=1, max_length=36)


class RolesReplace(StrictPayload):
    role_ids: list[str] = Field(max_length=1000)


class RoleCreate(StrictPayload):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    grants: list[str] = Field(default_factory=list)
    business_role_iri: str | None = Field(default=None, max_length=1024)
    business_role_ontology_id: str | None = Field(default=None, max_length=36)


class RoleUpdate(StrictPayload):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    grants: list[str] | None = None
    business_role_iri: str | None = Field(default=None, max_length=1024)
    business_role_ontology_id: str | None = Field(default=None, max_length=36)


def require_org(principal):
    if not principal.is_org_admin:
        raise HTTPException(403, detail={"code": "forbidden_scope"})


def require_project(principal, session, project_id):
    if "admin" not in principal.effective_scopes or (
        not principal.is_org_admin and principal.project_id != project_id
    ):
        raise HTTPException(403, detail={"code": "forbidden_scope"})
    if session.get(ProjectModel, project_id) is None:
        raise HTTPException(404, detail="Project not found")


def user_record(session, user_id):
    user = session.get(UserModel, user_id)
    if user is None:
        raise HTTPException(404, detail="User not found")
    return user


def member_record(session, project_id, user_id):
    if session.get(ProjectUserMembershipModel, (project_id, user_id)) is None:
        raise HTTPException(404, detail="Member not found")
    return user_record(session, user_id)


def user_read(user):
    return {
        "id": user.id,
        "username": user.username,
        "disabled_at": user.disabled_at,
        "is_org_admin": user.is_org_admin,
    }


def role_record(session, project_id, role_id):
    role = session.get(SemanticAccessRoleModel, role_id)
    if role is None or role.project_id != project_id:
        raise HTTPException(404, detail="Role not found")
    return role


def role_read(role, session, store, settings):
    return {
        "id": role.id,
        "project_id": role.project_id,
        "name": role.name,
        "description": role.description,
        "grants": role.grants,
        "business_role_iri": role.business_role_iri,
        "business_role_ontology_id": role.business_role_ontology_id,
        "business_role_status": business_role_status(
            session,
            store,
            settings,
            role.project_id,
            role.business_role_ontology_id,
            role.business_role_iri,
        ),
    }


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, principal: Principal, session: DB):
    require_org(principal)
    user = UserModel(id=str(uuid4()), username=payload.username, is_org_admin=False)
    session.add(user)
    commit_configuration(session)
    session.refresh(user)
    return user_read(user)


@router.get("/users")
def list_users(principal: Principal, session: DB):
    require_org(principal)
    return [user_read(user) for user in session.scalars(select(UserModel).order_by(UserModel.id))]


@router.get("/users/{user_id}")
def get_user(user_id: str, principal: Principal, session: DB):
    require_org(principal)
    return user_read(user_record(session, user_id))


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, principal: Principal, session: DB):
    require_org(principal)
    user = user_record(session, user_id)
    if "username" in payload.model_fields_set:
        if payload.username is None:
            raise HTTPException(422, detail="username cannot be null")
        user.username = payload.username
    if "disabled" in payload.model_fields_set:
        if payload.disabled is None:
            raise HTTPException(422, detail="disabled cannot be null")
        user.disabled_at = (user.disabled_at or datetime.now(UTC)) if payload.disabled else None
    commit_configuration(session)
    session.refresh(user)
    return user_read(user)


@router.get("/projects/{project_id}/members")
def list_members(project_id: str, principal: Principal, session: DB):
    require_project(principal, session, project_id)
    users = session.scalars(
        select(UserModel)
        .join(
            ProjectUserMembershipModel,
            ProjectUserMembershipModel.user_id == UserModel.id,
        )
        .where(ProjectUserMembershipModel.project_id == project_id)
        .order_by(UserModel.id)
    )
    return [
        {"user_id": user.id, "username": user.username, "project_id": project_id} for user in users
    ]


@router.post("/projects/{project_id}/members", status_code=201)
def add_member(project_id: str, payload: MemberCreate, principal: Principal, session: DB):
    require_org(principal)
    require_project(principal, session, project_id)
    user = user_record(session, payload.user_id)
    if session.get(ProjectUserMembershipModel, (project_id, user.id)) is None:
        session.add(ProjectUserMembershipModel(project_id=project_id, user_id=user.id))
        commit_configuration(session)
    return {"project_id": project_id, "user_id": user.id, "username": user.username}


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def delete_member(project_id: str, user_id: str, principal: Principal, session: DB):
    require_org(principal)
    require_project(principal, session, project_id)
    member_record(session, project_id, user_id)
    remove_member(session, project_id, user_id)
    return Response(status_code=204)


@router.get("/projects/{project_id}/members/{user_id}/roles")
def get_member_roles(project_id: str, user_id: str, principal: Principal, session: DB):
    require_project(principal, session, project_id)
    member_record(session, project_id, user_id)
    return {
        "project_id": project_id,
        "user_id": user_id,
        "role_ids": list(
            session.scalars(
                select(SemanticAccessRoleMemberModel.role_id)
                .where(
                    SemanticAccessRoleMemberModel.project_id == project_id,
                    SemanticAccessRoleMemberModel.user_id == user_id,
                )
                .order_by(SemanticAccessRoleMemberModel.role_id)
            )
        ),
    }


@router.put("/projects/{project_id}/members/{user_id}/roles")
def put_member_roles(
    project_id: str, user_id: str, payload: RolesReplace, principal: Principal, session: DB
):
    require_project(principal, session, project_id)
    member_record(session, project_id, user_id)
    replace_roles(session, project_id, user_id, payload.role_ids)
    return get_member_roles(project_id, user_id, principal, session)


@router.get("/projects/{project_id}/semantic-access-roles")
def list_roles(
    project_id: str,
    principal: Principal,
    session: DB,
    store=Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    require_project(principal, session, project_id)
    return [
        role_read(role, session, store, settings)
        for role in session.scalars(
            select(SemanticAccessRoleModel)
            .where(SemanticAccessRoleModel.project_id == project_id)
            .order_by(SemanticAccessRoleModel.id)
        )
    ]


@router.post("/projects/{project_id}/semantic-access-roles", status_code=201)
def create_role(
    project_id: str,
    payload: RoleCreate,
    principal: Principal,
    session: DB,
    store=Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    require_project(principal, session, project_id)
    record = save_role(session, store, settings, project_id, payload.model_dump())
    return role_read(record, session, store, settings)


@router.get("/projects/{project_id}/semantic-access-roles/{role_id}")
def get_role(
    project_id: str,
    role_id: str,
    principal: Principal,
    session: DB,
    store=Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    require_project(principal, session, project_id)
    return role_read(role_record(session, project_id, role_id), session, store, settings)


@router.patch("/projects/{project_id}/semantic-access-roles/{role_id}")
def update_role(
    project_id: str,
    role_id: str,
    payload: RoleUpdate,
    principal: Principal,
    session: DB,
    store=Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    require_project(principal, session, project_id)
    values = payload.model_dump(exclude_unset=True)
    if any(values.get(field, "absent") is None for field in ("name", "grants")):
        raise HTTPException(422, detail="name and grants cannot be null")
    record = save_role(
        session, store, settings, project_id, values, role_record(session, project_id, role_id)
    )
    return role_read(record, session, store, settings)


@router.delete("/projects/{project_id}/semantic-access-roles/{role_id}", status_code=204)
def delete_role(project_id: str, role_id: str, principal: Principal, session: DB):
    require_project(principal, session, project_id)
    record = role_record(session, project_id, role_id)
    session.execute(
        delete(SemanticAccessRoleMemberModel).where(
            SemanticAccessRoleMemberModel.project_id == project_id,
            SemanticAccessRoleMemberModel.role_id == role_id,
        )
    )
    session.delete(record)
    commit_configuration(session)
    return Response(status_code=204)
