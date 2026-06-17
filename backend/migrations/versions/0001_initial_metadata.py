"""initial metadata schema

Revision ID: 0001_initial_metadata
Revises:
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_metadata"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ontologies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_ontologies_project_name"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )

    op.create_table(
        "classes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parent_class_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("external_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ontology_id", "name", name="uq_classes_ontology_name"),
    )

    op.create_table(
        "ontology_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("schema_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ontology_id", "version_number", name="uq_ontology_versions_number"),
    )

    op.create_table(
        "constraints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("expression", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "property_defs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("multi_valued", sa.Boolean(), nullable=False),
        sa.Column("enum_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("external_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_id", "name", name="uq_property_defs_class_name"),
    )

    op.create_table(
        "relation_types",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ontology_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parent_relation_type_id", sa.String(length=36), nullable=True),
        sa.Column("source_class_id", sa.String(length=36), nullable=False),
        sa.Column("target_class_id", sa.String(length=36), nullable=False),
        sa.Column("inverse_name", sa.String(length=200), nullable=True),
        sa.Column("normalized_type", sa.String(length=200), nullable=False),
        sa.Column("external_mappings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_relation_type_id"], ["relation_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_class_id"], ["classes.id"]),
        sa.ForeignKeyConstraint(["target_class_id"], ["classes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ontology_id",
            "name",
            "source_class_id",
            "target_class_id",
            name="uq_relation_types_ontology_name_source_target",
        ),
    )


def downgrade() -> None:
    op.drop_table("relation_types")
    op.drop_table("property_defs")
    op.drop_table("constraints")
    op.drop_table("ontology_versions")
    op.drop_table("classes")
    op.drop_table("api_keys")
    op.drop_table("ontologies")
    op.drop_table("projects")
