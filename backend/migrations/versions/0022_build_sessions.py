"""add external Agent build sessions, checkpoints, and ontology leases

Revision ID: 0022_build_sessions
Revises: 0021_lightweight_evidence
Create Date: 2026-07-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0022_build_sessions"
down_revision: Union[str, None] = "0021_lightweight_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "build_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("client_session_id", sa.String(length=255), nullable=False),
        sa.Column("create_request_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_session_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("last_resume_request_id", sa.String(length=255), nullable=True),
        sa.Column("terminal_request_id", sa.String(length=255), nullable=True),
        sa.Column("terminal_request_hash", sa.String(length=64), nullable=True),
        sa.Column("completion_summary", sa.Text(), nullable=True),
        sa.Column(
            "unresolved_items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_build_sessions_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["previous_session_id"], ["build_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "client_session_id", name="uq_build_sessions_project_client"
        ),
    )
    op.create_index(
        "ix_build_sessions_project_status_activity",
        "build_sessions",
        ["project_id", "status", "last_activity_at"],
        unique=False,
    )

    op.create_table(
        "build_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("build_session_id", sa.String(length=36), nullable=False),
        sa.Column("client_checkpoint_id", sa.String(length=255), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=True),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "blockers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("related_batch_id", sa.String(length=36), nullable=True),
        sa.Column("reported_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "phase IN ('intake', 'modeling', 'verification', 'handoff')",
            name="ck_build_checkpoints_phase",
        ),
        sa.ForeignKeyConstraint(
            ["build_session_id"], ["build_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "build_session_id",
            "client_checkpoint_id",
            name="uq_build_checkpoints_session_client",
        ),
        sa.UniqueConstraint(
            "build_session_id", "sequence", name="uq_build_checkpoints_session_sequence"
        ),
    )
    op.create_index(
        "ix_build_checkpoints_session_created",
        "build_checkpoints",
        ["build_session_id", "sequence"],
        unique=False,
    )
    op.create_index(
        "ix_build_checkpoints_ontology",
        "build_checkpoints",
        ["ontology_id"],
        unique=False,
        postgresql_where=sa.text("ontology_id IS NOT NULL"),
    )

    op.create_table(
        "ontology_leases",
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("build_session_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("acquired_by", sa.String(length=255), nullable=True),
        sa.Column(
            "acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_request_id", sa.String(length=255), nullable=True),
        sa.Column("last_request_operation", sa.String(length=32), nullable=True),
        sa.Column("last_request_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["build_session_id"], ["build_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("ontology_id"),
    )
    op.create_index(
        "ix_ontology_leases_session", "ontology_leases", ["build_session_id"], unique=False
    )
    op.create_index(
        "ix_ontology_leases_expiry", "ontology_leases", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_table("ontology_leases")
    op.drop_table("build_checkpoints")
    op.drop_table("build_sessions")
