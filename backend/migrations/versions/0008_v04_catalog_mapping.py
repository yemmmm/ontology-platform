"""add v0.4 catalog, mapping, connector support

Revision ID: 0008_v04_catalog_mapping
Revises: 0007_publication_report
Create Date: 2026-06-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_v04_catalog_mapping"
down_revision: Union[str, None] = "0007_publication_report"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "relation_types",
        sa.Column(
            "scope_policy",
            sa.String(length=32),
            server_default="both",
            nullable=False,
        ),
    )
    op.add_column(
        "relation_types",
        sa.Column("symmetric", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "relation_types",
        sa.Column("transitive", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "relation_types",
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
    )
    op.add_column("relation_types", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("relation_types", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "data_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("authority_level", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("connection_policy", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_data_sources_project_name"),
    )
    op.create_table(
        "data_resources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("authority_level", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "name", name="uq_data_resources_source_name"),
    )
    op.create_table(
        "external_fields",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("data_resource_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("data_type", sa.String(length=80), nullable=False),
        sa.Column("sensitivity", sa.String(length=40), nullable=False),
        sa.Column("access_policy", sa.String(length=80), nullable=False),
        sa.Column("masking_rule", sa.String(length=200), nullable=True),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("audit_required", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_resource_id"], ["data_resources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_resource_id", "name", name="uq_external_fields_resource_name"),
    )
    op.create_table(
        "semantic_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("ontology_id", sa.String(length=36), nullable=True),
        sa.Column("ontology_version_id", sa.String(length=36), nullable=True),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("field_id", sa.String(length=36), nullable=False),
        sa.Column("external_resource_name", sa.String(length=200), nullable=False),
        sa.Column("external_field_name", sa.String(length=200), nullable=False),
        sa.Column("join_key", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["external_fields.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_version_id"], ["ontology_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["data_resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ontology_id",
            "target_type",
            "target_id",
            "field_id",
            name="uq_semantic_mapping_target_field",
        ),
    )
    op.create_table(
        "connector_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("allowed_field_ids", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("parameter_schema", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_schema", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("access_policy", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "name", name="uq_connector_templates_source_name"),
    )
    op.create_table(
        "connector_query_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("authorized", sa.Boolean(), nullable=False),
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.Column("parameters", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("queried_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["connector_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("connector_query_audits")
    op.drop_table("connector_templates")
    op.drop_table("semantic_mappings")
    op.drop_table("external_fields")
    op.drop_table("data_resources")
    op.drop_table("data_sources")
    op.drop_column("relation_types", "valid_to")
    op.drop_column("relation_types", "valid_from")
    op.drop_column("relation_types", "status")
    op.drop_column("relation_types", "transitive")
    op.drop_column("relation_types", "symmetric")
    op.drop_column("relation_types", "scope_policy")
