"""drop legacy governance and stage 1/2 tables (Stage 3 hard cut)

Revision ID: 0017_drop_legacy_governance
Revises: 0016_semantic_migration_tables
Create Date: 2026-07-06

Drops the legacy governance / publication / catalog tables and the
ontology_versions machinery that B2 already removed from the application
layer. One-way hard cut: legacy data cannot be reconstructed once dropped.
"""
from alembic import op

revision = "0017_drop_legacy_governance"
down_revision = "0016_semantic_migration_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the FK on semantic_mappings.ontology_version_id before removing
    # ontology_versions; the column itself stays (Stage 4 catalog rebuild will
    # retire SemanticMappingModel entirely).
    op.drop_constraint(
        "semantic_mappings_ontology_version_id_fkey",
        "semantic_mappings",
        type_="foreignkey",
    )

    # Plain column on ontologies (no FK constraint to drop).
    op.drop_column("ontologies", "current_version_id")

    # Drop legacy catalog tables (children of ontologies).
    # relation_types references classes (source_class_id, target_class_id),
    # so relation_types must go before classes. property_defs references
    # classes too.
    for table in ("relation_types", "property_defs", "constraints", "classes"):
        op.drop_table(table)

    # Drop legacy governance / publication / proposal machinery.
    # Order matters: children before parents.
    for table in (
        "review_decisions",
        "evidence",
        "review_batches",
        "validation_runs",
        "publication_gates",
        "fact_claims",
        "rule_definitions",
        "unanchored_knowledge",
        "knowledge_conflicts",
        "proposals",
        "ontology_versions",
    ):
        op.drop_table(table)


def downgrade() -> None:
    raise NotImplementedError(
        "Stage 3 hard-cut migration is one-way. Legacy data cannot be "
        "reconstructed once dropped. Restore from a pre-migration backup."
    )
