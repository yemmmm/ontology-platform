"""Add semantic runtime metadata tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_semantic_runtime_metadata"
down_revision: str | None = "0010_v05_assertions_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_graph_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_iri", sa.Text(), nullable=False),
        sa.Column("editable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("updated_by", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_iri", name="uq_semantic_graph_states_graph_iri"),
    )
    op.create_table(
        "semantic_validation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "data_graph_iris",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "shape_graph_iris",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("conforms", sa.Boolean()),
        sa.Column("report_graph_iri", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
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
    op.create_table(
        "semantic_reasoning_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "source_graph_iris",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("result_graph_iri", sa.Text()),
        sa.Column("reasoner", sa.String(length=255), server_default="command", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("consistent", sa.Boolean()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
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
    op.create_table(
        "semantic_projection_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "source_graph_iris",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("reasoning_result_graph_iri", sa.Text()),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("node_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("relationship_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
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
    op.drop_table("semantic_projection_jobs")
    op.drop_table("semantic_reasoning_runs")
    op.drop_table("semantic_validation_runs")
    op.drop_table("semantic_graph_states")
