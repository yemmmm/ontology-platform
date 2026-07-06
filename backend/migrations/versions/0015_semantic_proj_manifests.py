"""semantic projection manifests and graph-set-aware jobs

Revision ID: 0015_semantic_proj_manifests
Revises: 0014_semantic_rule_tables
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_semantic_proj_manifests"
down_revision = "0014_semantic_rule_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "semantic_projection_jobs",
        sa.Column("graph_set_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column(
            "projection_kind",
            sa.String(length=40),
            nullable=False,
            server_default="neo4j",
        ),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column(
            "projection_version",
            sa.String(length=80),
            nullable=False,
            server_default="neo4j-v1",
        ),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column(
            "projection_scope",
            sa.String(length=40),
            nullable=False,
            server_default="asserted",
        ),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column(
            "source_signature",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column(
            "input_graph_revisions",
            sa.JSON,
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column(
            "input_derived_pointers",
            sa.JSON,
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column("target_store", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column("target_partition", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column("rule_result_graph_iri", sa.Text(), nullable=True),
    )
    op.add_column(
        "semantic_projection_jobs",
        sa.Column(
            "document_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "semantic_projection_manifests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_set_id", sa.String(length=36), nullable=False),
        sa.Column("projection_kind", sa.String(length=40), nullable=False),
        sa.Column("active_job_id", sa.String(length=36), nullable=True),
        sa.Column(
            "source_signature",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "projection_version",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "target_partition",
            sa.String(length=255),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="current",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "graph_set_id",
            "projection_kind",
            "target_partition",
            name="uq_semantic_projection_manifests_set_kind_partition",
        ),
    )


def downgrade() -> None:
    op.drop_table("semantic_projection_manifests")
    for col in (
        "document_count",
        "rule_result_graph_iri",
        "target_partition",
        "target_store",
        "input_derived_pointers",
        "input_graph_revisions",
        "source_signature",
        "projection_scope",
        "projection_version",
        "projection_kind",
        "graph_set_id",
    ):
        with op.batch_alter_table("semantic_projection_jobs") as batch_op:
            batch_op.drop_column(col)
