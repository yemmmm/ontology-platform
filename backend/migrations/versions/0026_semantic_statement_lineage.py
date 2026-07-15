"""add statement occurrence lineage tables

Revision ID: 0026_semantic_statement_lineage
Revises: 0025_backfill_workspaces
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_semantic_statement_lineage"
down_revision: str | None = "0025_backfill_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "semantic_statement_occurrences",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("graph_set_id", sa.String(36)),
        sa.Column("statement_id", sa.String(64), nullable=False),
        sa.Column("subject_iri", sa.Text(), nullable=False),
        sa.Column("predicate_iri", sa.Text(), nullable=False),
        sa.Column("object_ntriples", sa.Text(), nullable=False),
        sa.Column("graph_iri", sa.Text(), nullable=False),
        sa.Column("graph_revision", sa.Integer(), nullable=False),
        sa.Column("assertion_kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("invalidated_revision", sa.Integer()),
        sa.Column("invalidated_by_audit_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "assertion_kind IN ('asserted','owl_inferred','construct_derived',"
            "'rule_derived','workflow_derived')",
            name="ck_semantic_statement_occurrence_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active','invalidated')",
            name="ck_semantic_statement_occurrence_status",
        ),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["graph_set_id"], ["semantic_graph_sets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["invalidated_by_audit_id"], ["semantic_edit_audits.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "statement_id",
            "graph_revision",
            name="uq_semantic_statement_occurrence_revision",
        ),
    )
    for suffix, columns in (
        ("ontology", ["ontology_id"]),
        ("statement", ["statement_id"]),
        ("subject", ["subject_iri"]),
        ("graph", ["graph_iri"]),
        ("status", ["status"]),
    ):
        op.create_index(
            f"ix_semantic_statement_occurrence_{suffix}",
            "semantic_statement_occurrences",
            columns,
        )

    op.create_table(
        "semantic_statement_origins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("statement_occurrence_id", sa.String(64), nullable=False),
        sa.Column("origin_kind", sa.String(32), nullable=False),
        sa.Column("origin_id", sa.String(255), nullable=False),
        sa.Column("metadata", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "origin_kind IN ('modeling_item','edit_audit','reasoning_run',"
            "'rule_run','legacy_unknown')",
            name="ck_semantic_statement_origin_kind",
        ),
        sa.ForeignKeyConstraint(
            ["statement_occurrence_id"],
            ["semantic_statement_occurrences.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "statement_occurrence_id",
            "origin_kind",
            "origin_id",
            name="uq_semantic_statement_origin",
        ),
    )
    op.create_index(
        "ix_semantic_statement_origin_occurrence",
        "semantic_statement_origins",
        ["statement_occurrence_id"],
    )
    op.create_index(
        "ix_semantic_statement_origin_target",
        "semantic_statement_origins",
        ["origin_kind", "origin_id"],
    )

    op.create_table(
        "semantic_statement_premises",
        sa.Column("derived_occurrence_id", sa.String(64), primary_key=True),
        sa.Column("premise_occurrence_id", sa.String(64), primary_key=True),
        sa.Column("proof_kind", sa.String(16), server_default="exact", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("proof_kind = 'exact'", name="ck_semantic_statement_premise_proof"),
        sa.ForeignKeyConstraint(
            ["derived_occurrence_id"],
            ["semantic_statement_occurrences.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["premise_occurrence_id"],
            ["semantic_statement_occurrences.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_semantic_statement_premise_derived",
        "semantic_statement_premises",
        ["derived_occurrence_id"],
    )
    op.create_index(
        "ix_semantic_statement_premise_premise",
        "semantic_statement_premises",
        ["premise_occurrence_id"],
    )


def downgrade() -> None:
    op.drop_table("semantic_statement_premises")
    op.drop_table("semantic_statement_origins")
    op.drop_table("semantic_statement_occurrences")
