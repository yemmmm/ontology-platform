"""Add v0.5 assertion, rule, and background knowledge storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_v05_assertions_rules"
down_revision: str | None = "0009_evidence_artifact_rename"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fact_claims",
        sa.Column(
            "anchor",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "fact_claims",
        sa.Column("sensitivity", sa.String(length=32), server_default="normal", nullable=False),
    )
    op.add_column(
        "fact_claims",
        sa.Column(
            "access_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("fact_claims", sa.Column("override_of_claim_id", sa.String(length=36)))

    op.create_table(
        "rule_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("ontology_version_id", sa.String(length=36), nullable=False),
        sa.Column("rule_type", sa.String(length=40), nullable=False),
        sa.Column(
            "scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "condition",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "conclusion",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column(
            "evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_from_proposal_id", sa.String(length=36)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_version_id"], ["ontology_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "unanchored_knowledge",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("ontology_version_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "source",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "embedding",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("applicability", sa.Text()),
        sa.Column("status", sa.String(length=32), server_default="background", nullable=False),
        sa.Column("promoted_proposal_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_version_id"], ["ontology_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("unanchored_knowledge")
    op.drop_table("rule_definitions")
    op.drop_column("fact_claims", "override_of_claim_id")
    op.drop_column("fact_claims", "access_policy")
    op.drop_column("fact_claims", "sensitivity")
    op.drop_column("fact_claims", "anchor")
