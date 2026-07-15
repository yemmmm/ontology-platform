"""allow project cleanup to cascade immutable modeling item results

Revision ID: 0024_modeling_result_cascade
Revises: 0023_modeling_batches
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_modeling_result_cascade"
down_revision: str | None = "0023_modeling_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "modeling_attempt_item_results_modeling_item_id_fkey",
        "modeling_attempt_item_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "modeling_attempt_item_results_modeling_item_id_fkey",
        "modeling_attempt_item_results",
        "modeling_items",
        ["modeling_item_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "modeling_attempt_item_results_modeling_item_id_fkey",
        "modeling_attempt_item_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "modeling_attempt_item_results_modeling_item_id_fkey",
        "modeling_attempt_item_results",
        "modeling_items",
        ["modeling_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
