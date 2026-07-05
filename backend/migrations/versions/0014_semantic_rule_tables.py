"""Add Phase 5 rule definitions and rule runs tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_semantic_rule_tables"
down_revision: str | None = "0013_semantic_graph_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_rule_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("rule_iri", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "input_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "output_kind", sa.String(length=40), server_default="assertion", nullable=False
        ),
        sa.Column(
            "uses_inferred_facts",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "requires_review", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "safety_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=255)),
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
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_iri", "version", name="uq_semantic_rule_definitions_iri_version"
        ),
    )
    op.create_index(
        "ix_semantic_rule_definitions_status",
        "semantic_rule_definitions",
        ["status"],
    )
    op.create_index(
        "ix_semantic_rule_definitions_language",
        "semantic_rule_definitions",
        ["language"],
    )

    op.create_table(
        "semantic_rule_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_set_id", sa.String(length=36), nullable=False),
        sa.Column("rule_definition_id", sa.String(length=36)),
        sa.Column("rule_version", sa.String(length=80)),
        sa.Column("result_graph_iri", sa.Text()),
        sa.Column("rule_run_graph_iri", sa.Text()),
        sa.Column("engine_name", sa.String(length=40), nullable=False),
        sa.Column("engine_version", sa.String(length=255)),
        sa.Column("source_signature", sa.String(length=128), server_default="", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column(
            "generated_statement_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["graph_set_id"], ["semantic_graph_sets.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_semantic_rule_runs_graph_set",
        "semantic_rule_runs",
        ["graph_set_id"],
    )
    op.create_index(
        "ix_semantic_rule_runs_status",
        "semantic_rule_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_semantic_rule_runs_status", table_name="semantic_rule_runs")
    op.drop_index("ix_semantic_rule_runs_graph_set", table_name="semantic_rule_runs")
    op.drop_table("semantic_rule_runs")
    op.drop_index(
        "ix_semantic_rule_definitions_language", table_name="semantic_rule_definitions"
    )
    op.drop_index(
        "ix_semantic_rule_definitions_status", table_name="semantic_rule_definitions"
    )
    op.drop_table("semantic_rule_definitions")
