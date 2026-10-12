"""Persist independent semantic usage feedback and append-only handling history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0036_semantic_feedback"
down_revision = "0035_ontology_model_revision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "semantic_feedback",
        sa.Column("feedback_id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("submitted_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission", JSONB, nullable=False),
        sa.Column("resolution_history", JSONB, nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
    )
    op.create_index(
        "ix_semantic_feedback_project_time",
        "semantic_feedback",
        ["project_id", "created_at", "feedback_id"],
    )


def downgrade():
    op.drop_table("semantic_feedback")
