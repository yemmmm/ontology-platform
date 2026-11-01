"""Project questions can precede an Ontology and bind fixed content revisions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0037_custom_cq"
down_revision = "0036_semantic_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("competency_questions", "ontology_id", nullable=True)
    op.add_column("competency_questions", sa.Column("external_id", sa.String(200), nullable=True))
    op.add_column(
        "competency_questions",
        sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "competency_questions",
        sa.Column("cq_definition", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_unique_constraint(
        "uq_cq_external_id", "competency_questions", ["project_id", "external_id"]
    )


def downgrade():
    # A project question cannot safely be assigned a made-up Ontology on downgrade.
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT count(*) FROM competency_questions WHERE ontology_id IS NULL")
    ):
        raise RuntimeError("Archive or bind project-level questions before downgrading custom CQ")
    op.drop_constraint("uq_cq_external_id", "competency_questions", type_="unique")
    for name in ("cq_definition", "content_revision", "external_id"):
        op.drop_column("competency_questions", name)
    op.alter_column("competency_questions", "ontology_id", nullable=False)
