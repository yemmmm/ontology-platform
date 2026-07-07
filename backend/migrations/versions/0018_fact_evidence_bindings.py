"""Add fact_evidence_bindings table.

Revision ID: 0018_fact_evidence_bindings
Revises: 0017_drop_legacy_governance
Create Date: 2026-07-08

New Postgres table for fact-level evidence bindings. Replaces the RDF
prov:wasDerivedFrom + chunk literal pattern. Each row binds one piece of
evidence (chunk reference or raw text) to a fact identified by fact_id
(sha256(s,p,o,g)). Distinct from evidence_chunks, which holds document
parser slices.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_fact_evidence_bindings"
down_revision: str | None = "0017_drop_legacy_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_evidence_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fact_id", sa.String(length=64), nullable=False),
        sa.Column("subject_iri", sa.Text(), nullable=False),
        sa.Column("predicate_iri", sa.Text(), nullable=False),
        sa.Column("object_value", sa.Text(), nullable=False),
        sa.Column("graph_iri", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("document_filename", sa.String(length=255), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["evidence_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["evidence_artifact_id"], ["evidence_artifacts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fact_evidence_bindings_fact_id"),
        "fact_evidence_bindings",
        ["fact_id"],
    )
    op.create_index(
        op.f("ix_fact_evidence_bindings_subject_iri"),
        "fact_evidence_bindings",
        ["subject_iri"],
    )
    op.create_index(
        "ix_fact_evidence_bindings_chunk_id_partial",
        "fact_evidence_bindings",
        ["chunk_id"],
        postgresql_where=sa.text("chunk_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fact_evidence_bindings_chunk_id_partial", table_name="fact_evidence_bindings"
    )
    op.drop_index(
        op.f("ix_fact_evidence_bindings_subject_iri"), table_name="fact_evidence_bindings"
    )
    op.drop_index(
        op.f("ix_fact_evidence_bindings_fact_id"), table_name="fact_evidence_bindings"
    )
    op.drop_table("fact_evidence_bindings")
