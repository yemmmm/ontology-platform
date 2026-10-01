"""Explicit role/user setup for pre-v4 access regression fixtures."""

from uuid import uuid4
from app.repositories.models import (
    ProjectUserMembershipModel,
    SemanticAccessRoleModel,
    SemanticAccessRoleMemberModel,
    UserModel,
)
from app.security.auth import create_api_key as issue_key


def create_api_key(session, *, name, project_id, scopes, semantic_grants=None, **kwargs):
    user = UserModel(
        id=str(uuid4()), username=f"fixture-{uuid4()}", is_org_admin=project_id is None
    )
    session.add(user)
    session.flush()
    if project_id:
        session.add(ProjectUserMembershipModel(project_id=project_id, user_id=user.id))
        session.flush()
        if semantic_grants:
            role = SemanticAccessRoleModel(
                id=str(uuid4()),
                project_id=project_id,
                name=f"fixture-{uuid4()}",
                grants=semantic_grants,
            )
            session.add(role)
            session.flush()
            session.add(
                SemanticAccessRoleMemberModel(
                    project_id=project_id, user_id=user.id, role_id=role.id
                )
            )
    session.commit()
    return issue_key(
        session, name=name, project_id=project_id, scopes=scopes, user_id=user.id, **kwargs
    )
