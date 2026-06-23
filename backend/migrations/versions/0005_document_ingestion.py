"""add document ingestion and knowledge candidate provenance

Revision ID: 0005_document_ingestion
Revises: 0004_interview_questions
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_document_ingestion"
down_revision: Union[str, None] = "0004_interview_questions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("parse_status", sa.String(32), nullable=False),
        sa.Column("parse_error", sa.Text()),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("parse_count", sa.Integer(), nullable=False),
        sa.Column("parse_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "content_hash", name="uq_source_documents_content"),
    )
    op.create_table(
        "source_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("parse_revision", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "document_id", "parse_revision", "sequence", name="uq_source_chunks_sequence"
        ),
    )
    op.create_foreign_key(
        "fk_evidence_document", "evidence", "source_documents", ["document_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_evidence_chunk", "evidence", "source_chunks", ["chunk_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "knowledge_conflicts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("item_key", sa.String(255), nullable=False),
        sa.Column("field", sa.String(255), nullable=False),
        sa.Column("existing_value", JSONB, nullable=False),
        sa.Column("proposed_value", JSONB, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("resolution", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("proposal_id", "item_key", "field", name="uq_knowledge_conflict_item"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_conflicts")
    op.drop_constraint("fk_evidence_chunk", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_document", "evidence", type_="foreignkey")
    op.drop_table("source_chunks")
    op.drop_table("source_documents")
