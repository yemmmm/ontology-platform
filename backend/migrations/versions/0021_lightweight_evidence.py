"""add lightweight project evidence references and associations

Revision ID: 0021_lightweight_evidence
Revises: 0020_default_ontology_workspace
Create Date: 2026-07-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_lightweight_evidence"
down_revision: Union[str, None] = "0020_default_ontology_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_document_name", sa.String(length=255), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "normalized_document_name",
            "excerpt_hash",
            name="uq_evidence_references_project_document_excerpt",
        ),
    )
    op.create_index(
        op.f("ix_evidence_references_project_id"),
        "evidence_references",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "evidence_associations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("graph_set_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_reference_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=512), nullable=False),
        sa.Column("client_item_id", sa.String(length=255), nullable=True),
        sa.Column("edit_audit_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_reference_id"], ["evidence_references.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["edit_audit_id"], ["semantic_edit_audits.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ontology_id",
            "target_type",
            "target_id",
            "evidence_reference_id",
            name="uq_evidence_associations_target_reference",
        ),
    )
    for column in (
        "project_id",
        "ontology_id",
        "graph_set_id",
        "evidence_reference_id",
        "edit_audit_id",
    ):
        op.create_index(
            op.f(f"ix_evidence_associations_{column}"),
            "evidence_associations",
            [column],
            unique=False,
        )
    op.add_column(
        "fact_evidence_bindings",
        sa.Column("evidence_reference_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_fact_evidence_reference",
        "fact_evidence_bindings",
        "evidence_references",
        ["evidence_reference_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_fact_evidence_bindings_evidence_reference_id"),
        "fact_evidence_bindings",
        ["evidence_reference_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_fact_evidence_bindings_evidence_reference_id"),
        table_name="fact_evidence_bindings",
    )
    op.drop_constraint(
        "fk_fact_evidence_reference", "fact_evidence_bindings", type_="foreignkey"
    )
    op.drop_column("fact_evidence_bindings", "evidence_reference_id")
    op.drop_table("evidence_associations")
    op.drop_table("evidence_references")
