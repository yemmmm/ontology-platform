"""Add semantic edit audit table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_semantic_edit_audits"
down_revision: str | None = "0011_semantic_runtime_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_edit_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.String(length=255)),
        sa.Column("reason", sa.Text()),
        sa.Column("input_format", sa.String(length=32), nullable=False),
        sa.Column("target_graph_iri", sa.Text()),
        sa.Column(
            "affected_graph_iris",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "graph_delta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("evidence_status", sa.String(length=64)),
        sa.Column(
            "warning_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("applied", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_semantic_edit_audits_created_at",
        "semantic_edit_audits",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_semantic_edit_audits_created_at", table_name="semantic_edit_audits")
    op.drop_table("semantic_edit_audits")
