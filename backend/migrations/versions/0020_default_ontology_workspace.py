"""Add the default ontology workspace marker and uniqueness constraint."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_default_ontology_workspace"
down_revision: str | None = "0019_simplify_rule_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "semantic_graph_sets",
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "uq_semantic_graph_sets_default_ontology",
        "semantic_graph_sets",
        ["scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_semantic_graph_sets_default_ontology", table_name="semantic_graph_sets"
    )
    op.drop_column("semantic_graph_sets", "is_default")
