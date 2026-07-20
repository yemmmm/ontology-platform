"""preserve asserted label evidence in retrieval documents

Revision ID: 0031_retrieval_label_evidence
Revises: 0030_retrieval_partition_id
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0031_retrieval_label_evidence"
down_revision: str | None = "0030_retrieval_partition_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "semantic_retrieval_documents",
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Preserve the only label old rows retained.  They are still marked stale
    # below because a full rebuild is required to recover additional labels.
    op.execute(
        """
        UPDATE semantic_retrieval_documents
           SET labels = jsonb_build_array(
                 jsonb_build_object(
                   'predicate', 'http://www.w3.org/2000/01/rdf-schema#label',
                   'value', label,
                   'language', ''
                 )
               )
         WHERE label IS NOT NULL AND label <> ''
        """
    )
    op.execute(
        """
        UPDATE semantic_projection_manifests
           SET status = 'stale'
         WHERE projection_kind = 'vector' AND status = 'current'
        """
    )


def downgrade() -> None:
    op.drop_column("semantic_retrieval_documents", "labels")
