"""scope relation type names by source and target classes

Revision ID: 0002_relation_type_name_scope
Revises: 0001_initial_metadata
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_relation_type_name_scope"
down_revision: Union[str, None] = "0001_initial_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _unique_constraint_names(table_name: str) -> set[str]:
    """Return the named unique constraints currently present on a table."""
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
        if constraint["name"] is not None
    }


def upgrade() -> None:
    constraints = _unique_constraint_names("relation_types")
    if "uq_relation_types_ontology_name" in constraints:
        op.drop_constraint(
            "uq_relation_types_ontology_name",
            "relation_types",
            type_="unique",
        )
    if "uq_relation_types_ontology_name_source_target" not in constraints:
        op.create_unique_constraint(
            "uq_relation_types_ontology_name_source_target",
            "relation_types",
            ["ontology_id", "name", "source_class_id", "target_class_id"],
        )


def downgrade() -> None:
    constraints = _unique_constraint_names("relation_types")
    if "uq_relation_types_ontology_name_source_target" in constraints:
        op.drop_constraint(
            "uq_relation_types_ontology_name_source_target",
            "relation_types",
            type_="unique",
        )
    if "uq_relation_types_ontology_name" not in constraints:
        op.create_unique_constraint(
            "uq_relation_types_ontology_name",
            "relation_types",
            ["ontology_id", "name"],
        )
