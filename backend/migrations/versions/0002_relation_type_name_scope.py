"""scope relation type names by source and target classes

Revision ID: 0002_relation_type_name_scope
Revises: 0001_initial_metadata
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_relation_type_name_scope"
down_revision: Union[str, None] = "0001_initial_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_relation_types_ontology_name",
        "relation_types",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_relation_types_ontology_name_source_target",
        "relation_types",
        ["ontology_id", "name", "source_class_id", "target_class_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_relation_types_ontology_name_source_target",
        "relation_types",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_relation_types_ontology_name",
        "relation_types",
        ["ontology_id", "name"],
    )
