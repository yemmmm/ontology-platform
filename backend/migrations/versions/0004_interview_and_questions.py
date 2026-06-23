"""add project interview and competency question workflow

Revision ID: 0004_interview_questions
Revises: 0003_governance_foundation
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_interview_questions"
down_revision: Union[str, None] = "0003_governance_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "project_briefs",
        sa.Column("field_states", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column(
        "project_briefs",
        sa.Column("field_sources", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column(
        "competency_questions", sa.Column("position", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "competency_questions", sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column(
        "competency_questions",
        sa.Column("source_answer_ids", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "competency_questions",
        sa.Column("source_brief_fields", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_table(
        "interview_answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("interview_answers")
    for column in ["source_brief_fields", "source_answer_ids", "active", "position"]:
        op.drop_column("competency_questions", column)
    op.drop_column("project_briefs", "field_sources")
    op.drop_column("project_briefs", "field_states")
