"""R3.0-004 subject-bound semantic knowledge access control.

Revision ID: 0032_semantic_protection_sets
Revises: 0031_retrieval_label_evidence
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0032_semantic_protection_sets"
down_revision: str | None = "0031_retrieval_label_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "semantic_protection_sets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "allowed_grants",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_protection_set_project_name"),
    )
    op.create_index(
        "ix_semantic_protection_sets_project_id",
        "semantic_protection_sets",
        ["project_id"],
    )
    op.create_table(
        "semantic_protection_set_members",
        sa.Column("protection_set_id", sa.String(length=36), nullable=False),
        sa.Column("resource_iri", sa.String(length=1024), nullable=False),
        # Deliberately no FK to ontologies: dangling ontology ids are a legal
        # persistent state (member rows must survive ontology deletion).
        sa.Column("ontology_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["protection_set_id"],
            ["semantic_protection_sets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("protection_set_id", "resource_iri"),
    )
    op.add_column(
        "api_keys",
        sa.Column("semantic_grants", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "semantic_grants")
    op.drop_table("semantic_protection_set_members")
    op.drop_index(
        "ix_semantic_protection_sets_project_id", table_name="semantic_protection_sets"
    )
    op.drop_table("semantic_protection_sets")
