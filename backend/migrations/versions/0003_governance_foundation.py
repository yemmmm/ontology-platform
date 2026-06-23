"""add v0.3 governance foundation

Revision ID: 0003_governance_foundation
Revises: 0002_relation_type_name_scope
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_governance_foundation"
down_revision: Union[str, None] = "0002_relation_type_name_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("ontology_versions", sa.Column("parent_version_id", sa.String(36)))
    op.add_column(
        "ontology_versions",
        sa.Column("workflow_status", sa.String(32), server_default="gathering", nullable=False),
    )
    op.add_column(
        "ontology_versions",
        sa.Column("graph_snapshot", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column("ontology_versions", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_ontology_versions_parent", "ontology_versions", "ontology_versions",
        ["parent_version_id"], ["id"], ondelete="SET NULL"
    )

    op.create_table(
        "project_briefs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False, unique=True),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "competency_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("query_definition", JSONB, nullable=False),
        sa.Column("validation_result", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("target_version_id", sa.String(36), nullable=False),
        sa.Column("proposal_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_by_type", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(255)),
        sa.Column("model_identifier", sa.String(255)),
        sa.Column("prompt_version", sa.String(255)),
        sa.Column("validation_result", JSONB, nullable=False),
        sa.Column("review_result", JSONB, nullable=False),
        sa.Column("application_result", JSONB, nullable=False),
        sa.Column("audit_log", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_version_id"], ["ontology_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_proposals_project_idempotency"),
    )
    op.create_table(
        "review_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stable_key", sa.String(255), nullable=False, unique=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("ontology_version_id", sa.String(36), nullable=False),
        sa.Column("review_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("item_ids", JSONB, nullable=False),
        sa.Column("counts", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_version_id"], ["ontology_versions.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("document_id", sa.String(36)),
        sa.Column("page_number", sa.Integer()),
        sa.Column("chunk_id", sa.String(100)),
        sa.Column("char_start", sa.Integer()),
        sa.Column("char_end", sa.Integer()),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reviewer_type", sa.String(40), nullable=False),
        sa.Column("reviewer_id", sa.String(255)),
        sa.Column("reason", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "validation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("errors", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "publication_gates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ontology_version_id", sa.String(36), nullable=False),
        sa.Column("gate_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("details", JSONB, nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["ontology_version_id"], ["ontology_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("ontology_version_id", "gate_type", name="uq_publication_gate_type"),
    )


def downgrade() -> None:
    for table in [
        "publication_gates", "validation_runs", "review_decisions", "evidence",
        "review_batches", "proposals", "competency_questions", "project_briefs",
    ]:
        op.drop_table(table)
    op.drop_constraint("fk_ontology_versions_parent", "ontology_versions", type_="foreignkey")
    op.drop_column("ontology_versions", "published_at")
    op.drop_column("ontology_versions", "graph_snapshot")
    op.drop_column("ontology_versions", "workflow_status")
    op.drop_column("ontology_versions", "parent_version_id")
