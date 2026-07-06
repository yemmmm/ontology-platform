"""semantic migration runs, batches, and parity reports

Revision ID: 0016_semantic_migration_tables
Revises: 0015_semantic_proj_manifests
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_semantic_migration_tables"
down_revision = "0015_semantic_proj_manifests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "semantic_migration_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_id", sa.String(length=255), nullable=True),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "phase2_mapping_version",
            sa.String(length=80),
            nullable=False,
            server_default="phase2-v1",
        ),
        sa.Column(
            "source_snapshot_signature",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
        sa.Column("target_graph_set_id", sa.String(length=36), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_semantic_migration_runs_scope",
        "semantic_migration_runs",
        ["scope_type", "scope_id"],
    )
    op.create_index(
        "ix_semantic_migration_runs_status",
        "semantic_migration_runs",
        ["status"],
    )

    op.create_table(
        "semantic_migration_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("migration_run_id", sa.String(length=36), nullable=False),
        sa.Column("batch_index", sa.Integer(), nullable=False),
        sa.Column("object_kind", sa.String(length=40), nullable=False),
        sa.Column("source_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("target_graph_iris", sa.JSON, nullable=False, server_default="[]"),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "inserted_quad_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "deleted_quad_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "source_hash",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
        sa.Column("target_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["migration_run_id"],
            ["semantic_migration_runs.id"],
            ondelete="CASCADE",
            name="fk_semantic_migration_batches_run_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_semantic_migration_batches_run",
        "semantic_migration_batches",
        ["migration_run_id", "batch_index"],
    )
    op.create_index(
        "ix_semantic_migration_batches_status",
        "semantic_migration_batches",
        ["status"],
    )

    op.create_table(
        "semantic_migration_parity_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("migration_run_id", sa.String(length=36), nullable=False),
        sa.Column("check_name", sa.String(length=80), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("legacy_count", sa.Integer(), nullable=True),
        sa.Column("rdf_count", sa.Integer(), nullable=True),
        sa.Column("diff_summary", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("sample_diffs", sa.JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["migration_run_id"],
            ["semantic_migration_runs.id"],
            ondelete="CASCADE",
            name="fk_semantic_migration_parity_reports_run_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_semantic_migration_parity_reports_run",
        "semantic_migration_parity_reports",
        ["migration_run_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_semantic_migration_parity_reports_run",
        table_name="semantic_migration_parity_reports",
    )
    op.drop_table("semantic_migration_parity_reports")
    op.drop_index(
        "ix_semantic_migration_batches_status",
        table_name="semantic_migration_batches",
    )
    op.drop_index(
        "ix_semantic_migration_batches_run",
        table_name="semantic_migration_batches",
    )
    op.drop_table("semantic_migration_batches")
    op.drop_index(
        "ix_semantic_migration_runs_status",
        table_name="semantic_migration_runs",
    )
    op.drop_index(
        "ix_semantic_migration_runs_scope",
        table_name="semantic_migration_runs",
    )
    op.drop_table("semantic_migration_runs")
