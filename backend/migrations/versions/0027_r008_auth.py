"""add R-008 users and security audit events

Revision ID: 0027_r008_auth
Revises: 0026_semantic_statement_lineage
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_r008_auth"
down_revision: str | None = "0026_semantic_statement_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(200), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("session_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(255)),
        sa.Column("auth_method", sa.String(32)),
        sa.Column("project_id", sa.String(36)),
        sa.Column("resource_type", sa.String(80)),
        sa.Column("resource_id", sa.String(255)),
        sa.Column(
            "details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_security_audit_events_created", "security_audit_events", ["created_at"])
    op.create_index(
        "ix_security_audit_events_project",
        "security_audit_events",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("security_audit_events")
    op.drop_table("users")
