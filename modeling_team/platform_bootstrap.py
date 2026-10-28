"""Host-only local credential bootstrap, independent of the legacy Team CLI."""

from __future__ import annotations

import sys
from pathlib import Path

from .contracts import TeamConfigurationError


def bootstrap_helpers(root: Path):
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    from app.core.config import Settings
    from app.repositories.models import ApiKeyModel
    from app.repositories.postgres import create_session_factory
    from app.security.auth import create_api_key, revoke_key
    from sqlalchemy import select

    def create() -> tuple[str, str]:
        with create_session_factory(Settings(_env_file=backend / ".env"))() as session:
            operator = session.scalar(
                select(ApiKeyModel).where(ApiKeyModel.name == "operator-admin")
            )
            if operator is None or operator.revoked_at is not None or not operator.user_id:
                raise TeamConfigurationError("enabled operator-admin user binding is required")
            record, plaintext = create_api_key(
                session,
                name="r2-3-001-team-runner-admin",
                project_id=None,
                scopes=["admin"],
                user_id=operator.user_id,
            )
        return plaintext, record.id

    def revoke(key_id: str) -> bool:
        with create_session_factory(Settings(_env_file=backend / ".env"))() as session:
            record = session.get(ApiKeyModel, key_id)
            return bool(record and revoke_key(session, record).revoked_at)

    return create, revoke
