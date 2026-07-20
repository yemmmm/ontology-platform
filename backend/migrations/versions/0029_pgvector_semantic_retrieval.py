"""add pgvector-backed semantic retrieval projection

Revision ID: 0029_pgvector_semantic_retrieval
Revises: 0028_modeling_workflow_records
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0029_pgvector_semantic_retrieval"
down_revision: str | None = "0028_modeling_workflow_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # Fail fast when deployment did not use the pgvector-enabled PostgreSQL
    # image.  A silent text/JSON fallback would make complete no-match unsafe.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "semantic_retrieval_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("graph_set_id", sa.String(36), nullable=False),
        sa.Column("workspace_version", sa.String(120), nullable=False),
        sa.Column("source_signature", sa.String(128), nullable=False),
        sa.Column("rule_set_signature", sa.String(128), nullable=False, server_default=""),
        sa.Column("resource_iri", sa.Text(), nullable=False),
        sa.Column("resource_kind", sa.String(32), nullable=False),
        sa.Column("assertion_kind", sa.String(32), nullable=False, server_default="asserted"),
        sa.Column("label", sa.Text()),
        sa.Column("aliases", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("descriptions", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("mapping_evidence", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rdf_types", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("document_text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("embedding_config_hash", sa.String(64), nullable=False),
        sa.Column("projection_version", sa.String(120), nullable=False),
        sa.Column("visibility", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("build_job_id", sa.String(36), nullable=False),
        sa.Column("target_partition", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "ontology_id",
            "workspace_version",
            "source_signature",
            "resource_iri",
            "resource_kind",
            "projection_version",
            "embedding_config_hash",
            name="uq_semantic_retrieval_document_current_input",
        ),
    )
    # Alembic cannot render vector dimensions with a generic type.  Alter the
    # new column explicitly; this remains a real vector(1024), not a text cast.
    op.execute(
        "ALTER TABLE semantic_retrieval_documents "
        "ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)"
    )
    op.create_index(
        "ix_semantic_retrieval_scope",
        "semantic_retrieval_documents",
        [
            "ontology_id",
            "workspace_version",
            "source_signature",
            "resource_kind",
            "projection_version",
            "embedding_config_hash",
        ],
    )
    op.create_index(
        "ix_semantic_retrieval_partition",
        "semantic_retrieval_documents",
        ["target_partition", "build_job_id"],
    )
    op.execute(
        "CREATE INDEX ix_semantic_retrieval_normalized_text_trgm "
        "ON semantic_retrieval_documents USING gin (normalized_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_table("semantic_retrieval_documents")
    # Extensions can be shared by another application schema.  Leave them in
    # place so downgrade never removes a dependency it cannot prove it owns.
