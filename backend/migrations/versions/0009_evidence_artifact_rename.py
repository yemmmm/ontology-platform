"""rename source documents to evidence artifacts

Revision ID: 0009_evidence_artifact_rename
Revises: 0008_v04_catalog_mapping
Create Date: 2026-06-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009_evidence_artifact_rename"
down_revision: Union[str, None] = "0008_v04_catalog_mapping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("source_documents", "evidence_artifacts")
    op.rename_table("source_chunks", "evidence_chunks")
    op.execute(
        "ALTER TABLE evidence_artifacts RENAME CONSTRAINT "
        "uq_source_documents_content TO uq_evidence_artifacts_content"
    )
    op.execute(
        "ALTER TABLE evidence_chunks RENAME CONSTRAINT "
        "uq_source_chunks_sequence TO uq_evidence_chunks_sequence"
    )
    op.execute("ALTER TABLE evidence RENAME CONSTRAINT fk_evidence_document TO fk_evidence_artifact")
    op.execute("ALTER TABLE evidence RENAME CONSTRAINT fk_evidence_chunk TO fk_evidence_artifact_chunk")


def downgrade() -> None:
    op.execute("ALTER TABLE evidence RENAME CONSTRAINT fk_evidence_artifact_chunk TO fk_evidence_chunk")
    op.execute("ALTER TABLE evidence RENAME CONSTRAINT fk_evidence_artifact TO fk_evidence_document")
    op.execute(
        "ALTER TABLE evidence_chunks RENAME CONSTRAINT "
        "uq_evidence_chunks_sequence TO uq_source_chunks_sequence"
    )
    op.execute(
        "ALTER TABLE evidence_artifacts RENAME CONSTRAINT "
        "uq_evidence_artifacts_content TO uq_source_documents_content"
    )
    op.rename_table("evidence_chunks", "source_chunks")
    op.rename_table("evidence_artifacts", "source_documents")
