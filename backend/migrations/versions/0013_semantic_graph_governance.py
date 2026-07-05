"""Add Phase 4 named-graph governance tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_semantic_graph_governance"
down_revision: str | None = "0012_semantic_edit_audits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_graph_registry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_iri", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("semantic_owner_type", sa.String(length=40)),
        sa.Column("semantic_owner_id", sa.String(length=255)),
        sa.Column(
            "mutable_by_direct_edit",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("managed", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.UniqueConstraint("graph_iri", name="uq_semantic_graph_registry_graph_iri"),
    )
    op.create_index(
        "ix_semantic_graph_registry_category",
        "semantic_graph_registry",
        ["category"],
    )

    op.create_table(
        "semantic_graph_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_iri", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("last_edit_audit_id", sa.String(length=36)),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("changed_by", sa.String(length=255)),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_iri", name="uq_semantic_graph_revisions_graph_iri"),
    )

    op.create_table(
        "semantic_graph_sets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_id", sa.String(length=255)),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("source_signature", sa.String(length=128), server_default="", nullable=False),
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
    )
    op.create_index(
        "ix_semantic_graph_sets_scope",
        "semantic_graph_sets",
        ["scope_type", "scope_id"],
    )

    op.create_table(
        "semantic_graph_set_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "graph_set_id",
            sa.String(length=36),
            sa.ForeignKey("semantic_graph_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("graph_iri", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "graph_set_id",
            "graph_iri",
            name="uq_semantic_graph_set_members_set_graph",
        ),
    )

    op.create_table(
        "semantic_derived_result_pointers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_set_id", sa.String(length=36)),
        sa.Column("result_kind", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("result_graph_iri", sa.Text(), nullable=False),
        sa.Column("source_signature", sa.String(length=128), server_default="", nullable=False),
        sa.Column("engine_name", sa.String(length=255)),
        sa.Column("engine_version", sa.String(length=255)),
        sa.Column("rule_version", sa.String(length=255)),
        sa.Column("shape_version", sa.String(length=255)),
        sa.Column("status", sa.String(length=32), server_default="current", nullable=False),
        sa.Column("became_current_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_semantic_derived_result_pointers_set_kind",
        "semantic_derived_result_pointers",
        ["graph_set_id", "result_kind", "status"],
    )

    op.create_table(
        "semantic_graph_gc_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("target_kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deleted_count", sa.Integer(), server_default="0", nullable=False),
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
    )


def downgrade() -> None:
    op.drop_table("semantic_graph_gc_runs")
    op.drop_index(
        "ix_semantic_derived_result_pointers_set_kind",
        table_name="semantic_derived_result_pointers",
    )
    op.drop_table("semantic_derived_result_pointers")
    op.drop_table("semantic_graph_set_members")
    op.drop_index("ix_semantic_graph_sets_scope", table_name="semantic_graph_sets")
    op.drop_table("semantic_graph_sets")
    op.drop_table("semantic_graph_revisions")
    op.drop_index(
        "ix_semantic_graph_registry_category",
        table_name="semantic_graph_registry",
    )
    op.drop_table("semantic_graph_registry")
