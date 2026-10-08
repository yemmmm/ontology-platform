"""Use Ontology model revisions for live write and projection bindings.

Old hashes remain in their original columns as historical evidence. They are
not translated into current model revisions. Disposable projections become
stale; pending old jobs/attempts must be re-prepared against a current read.
"""

from alembic import op
import sqlalchemy as sa

revision = "0035_ontology_model_revision"
down_revision = "0034_ontology_single_model"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("expected_model_revision", "model_revision_before", "model_revision_after"):
        op.add_column("modeling_batch_attempts", sa.Column(name, sa.Integer(), nullable=True))
    op.alter_column("modeling_batch_attempts", "expected_workspace_version", nullable=True)
    for table in (
        "semantic_projection_jobs",
        "semantic_projection_manifests",
        "semantic_retrieval_documents",
    ):
        op.add_column(table, sa.Column("model_revision", sa.Integer(), nullable=True))
    for name in ("workspace_version", "source_signature"):
        op.alter_column("semantic_retrieval_documents", name, nullable=True)
    # Preserve job/document rows and all original bindings; never label them current.
    op.execute("UPDATE semantic_projection_manifests SET status='stale' WHERE status='current'")
    op.execute(
        "UPDATE semantic_projection_jobs SET status='stale' WHERE status IN ('pending', 'running')"
    )
    op.drop_constraint(
        "uq_semantic_retrieval_document_current_input",
        "semantic_retrieval_documents",
        type_="unique",
    )
    op.drop_index("ix_semantic_retrieval_scope", table_name="semantic_retrieval_documents")
    op.create_unique_constraint(
        "uq_semantic_retrieval_document_current_input",
        "semantic_retrieval_documents",
        [
            "ontology_id",
            "model_revision",
            "resource_iri",
            "resource_kind",
            "projection_version",
            "embedding_config_hash",
            "build_job_id",
        ],
    )
    op.create_index(
        "ix_semantic_retrieval_scope",
        "semantic_retrieval_documents",
        [
            "ontology_id",
            "model_revision",
            "resource_kind",
            "projection_version",
            "embedding_config_hash",
        ],
    )


def downgrade():
    raise RuntimeError(
        "R4.0-027 bindings require explicit rollback; historical hashes cannot represent new revisions"
    )
