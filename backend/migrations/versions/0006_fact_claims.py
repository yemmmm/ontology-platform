"""add fact claims for v0.3 phase 5

Revision ID: 0006_fact_claims
Revises: 0005_document_ingestion
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_fact_claims"
down_revision: Union[str, None] = "0005_document_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "fact_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_key", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("ontology_version_id", sa.String(36), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False),
        sa.Column("layer", sa.String(64), nullable=False),
        sa.Column("subject", JSONB, nullable=False),
        sa.Column("predicate", sa.String(255), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("graph_path", JSONB, nullable=False),
        sa.Column("evidence_ids", JSONB, nullable=False),
        sa.Column("generation_reason", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("audit_status", sa.String(32), nullable=False),
        sa.Column("review_decision", JSONB, nullable=False),
        sa.Column("linked_fix_proposal_id", sa.String(36)),
        sa.Column("stale", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("stale_reason", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_version_id"], ["ontology_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("ontology_version_id", "claim_key", name="uq_fact_claims_version_key"),
    )


def downgrade() -> None:
    op.drop_table("fact_claims")
