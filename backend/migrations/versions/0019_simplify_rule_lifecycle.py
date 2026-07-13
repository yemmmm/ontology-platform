"""Simplify semantic rule lifecycle to immediately active rules."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_simplify_rule_lifecycle"
down_revision: str | None = "0018_fact_evidence_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "semantic_rule_definitions",
        "status",
        server_default="active",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.execute("UPDATE semantic_rule_definitions SET status = 'active'")


def downgrade() -> None:
    op.alter_column(
        "semantic_rule_definitions",
        "status",
        server_default="draft",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
