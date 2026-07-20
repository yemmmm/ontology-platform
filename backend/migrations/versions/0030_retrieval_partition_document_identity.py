"""partition retrieval document identity by immutable build job

Revision ID: 0030_retrieval_partition_document_identity
Revises: 0029_pgvector_semantic_retrieval
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0030_retrieval_partition_id"
down_revision: str | None = "0029_pgvector_semantic_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_semantic_retrieval_document_current_input",
        "semantic_retrieval_documents",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_semantic_retrieval_document_current_input",
        "semantic_retrieval_documents",
        [
            "ontology_id",
            "workspace_version",
            "source_signature",
            "resource_iri",
            "resource_kind",
            "projection_version",
            "embedding_config_hash",
            "build_job_id",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_semantic_retrieval_document_current_input",
        "semantic_retrieval_documents",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_semantic_retrieval_document_current_input",
        "semantic_retrieval_documents",
        [
            "ontology_id",
            "workspace_version",
            "source_signature",
            "resource_iri",
            "resource_kind",
            "projection_version",
            "embedding_config_hash",
        ],
    )
