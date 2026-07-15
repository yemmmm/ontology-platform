"""add R-004 modeling batches, attempts, fences, and versioned rules

Revision ID: 0023_modeling_batches
Revises: 0022_build_sessions
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_modeling_batches"
down_revision: str | None = "0022_build_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "modeling_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("build_session_id", sa.String(36), nullable=False),
        sa.Column("client_batch_id", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('open','applying','recovering','applied','partially_applied','failed')",
            name="ck_modeling_batches_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["build_session_id"], ["build_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "build_session_id", "client_batch_id", name="uq_modeling_batches_session_client"
        ),
    )
    op.create_index(
        "ix_modeling_batches_session_created",
        "modeling_batches",
        ["build_session_id", "created_at", "id"],
    )
    op.create_index(
        "ix_modeling_batches_ontology_created",
        "modeling_batches",
        ["ontology_id", "created_at", "id"],
    )

    op.create_table(
        "modeling_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("client_item_id", sa.String(255), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("command_kind", sa.String(80), nullable=False),
        sa.Column("payload", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("depends_on", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("resource_outputs", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "evidence_reference_ids", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("evidence", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column(
            "competency_question_ids", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["modeling_batches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("batch_id", "client_item_id", name="uq_modeling_items_batch_client"),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_modeling_items_batch_ordinal"),
    )

    op.create_table(
        "modeling_batch_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("build_session_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default="validating", nullable=False),
        sa.Column("expected_workspace_version", sa.String(128), nullable=False),
        sa.Column("graph_set_id", sa.String(36)),
        sa.Column("lease_revision", sa.Integer()),
        sa.Column("workspace_version_before", sa.String(128)),
        sa.Column("workspace_version_after", sa.String(128)),
        sa.Column("target_snapshot", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("normalized_delta", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("delta_hash", sa.String(64)),
        sa.Column("operation_plan", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("operation_plan_hash", sa.String(64)),
        sa.Column("findings", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("groups", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("recovery_state", sa.String(40), server_default="not_required", nullable=False),
        sa.Column("recovery_detail", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("audit_id", sa.String(36)),
        sa.Column("execution_claim_id", sa.String(36)),
        sa.Column("execution_claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("execution_claim_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "mode IN ('dry_run','apply_atomic','apply_partial')", name="ck_modeling_attempts_mode"
        ),
        sa.CheckConstraint(
            "status IN ('validating','validated','validation_failed','applying',"
            "'recovering','applied','partially_applied','failed')",
            name="ck_modeling_attempts_status",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["modeling_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["build_session_id"], ["build_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "build_session_id", "idempotency_key", name="uq_modeling_attempts_session_key"
        ),
    )
    op.create_index(
        "ix_modeling_attempts_batch_created", "modeling_batch_attempts", ["batch_id", "created_at"]
    )
    op.create_index(
        "uq_modeling_attempts_batch_inflight_apply",
        "modeling_batch_attempts",
        ["batch_id"],
        unique=True,
        postgresql_where=sa.text(
            "mode <> 'dry_run' AND status IN ('validating','applying','recovering')"
        ),
    )

    op.create_table(
        "modeling_attempt_item_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("attempt_id", sa.String(36), nullable=False),
        sa.Column("modeling_item_id", sa.String(36), nullable=False),
        sa.Column("client_item_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("atomic_group_id", sa.String(36)),
        sa.Column("resource_outputs", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("finding_codes", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "evidence_reference_ids", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "evidence_association_ids", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('validated','failed','not_applied','blocked','applied')",
            name="ck_modeling_item_results_status",
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["modeling_batch_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["modeling_item_id"], ["modeling_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "attempt_id", "modeling_item_id", name="uq_modeling_item_results_attempt_item"
        ),
    )

    op.create_table(
        "ontology_write_fences",
        sa.Column("ontology_id", sa.String(36), primary_key=True),
        sa.Column("attempt_id", sa.String(36), nullable=False, unique=True),
        sa.Column("build_session_id", sa.String(36), nullable=False),
        sa.Column("lease_revision", sa.Integer(), nullable=False),
        sa.Column(
            "acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["modeling_batch_attempts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["build_session_id"], ["build_sessions.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "semantic_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("rule_iri", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("current_definition_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_semantic_rules_status"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("ontology_id", "rule_iri", name="uq_semantic_rules_ontology_iri"),
    )
    op.create_index("ix_semantic_rules_ontology_id", "semantic_rules", ["ontology_id"])
    op.add_column("semantic_rule_definitions", sa.Column("semantic_rule_id", sa.String(36)))
    op.add_column("semantic_rule_definitions", sa.Column("definition_hash", sa.String(64)))
    op.drop_constraint(
        "uq_semantic_rule_definitions_iri_version",
        "semantic_rule_definitions",
        type_="unique",
    )
    op.create_foreign_key(
        "fk_semantic_rule_definitions_rule",
        "semantic_rule_definitions",
        "semantic_rules",
        ["semantic_rule_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_semantic_rule_definitions_semantic_rule_id",
        "semantic_rule_definitions",
        ["semantic_rule_id"],
    )
    op.create_index(
        "uq_semantic_rule_definitions_legacy_iri_version",
        "semantic_rule_definitions",
        ["rule_iri", "version"],
        unique=True,
        postgresql_where=sa.text("semantic_rule_id IS NULL"),
    )
    op.create_index(
        "uq_semantic_rule_definitions_rule_version",
        "semantic_rule_definitions",
        ["semantic_rule_id", "version"],
        unique=True,
        postgresql_where=sa.text("semantic_rule_id IS NOT NULL"),
    )
    op.create_foreign_key(
        "fk_semantic_rules_current_definition",
        "semantic_rules",
        "semantic_rule_definitions",
        ["current_definition_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_foreign_key(
        "fk_build_checkpoints_related_batch",
        "build_checkpoints",
        "modeling_batches",
        ["related_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_build_checkpoints_related_batch", "build_checkpoints", type_="foreignkey"
    )
    op.drop_constraint("fk_semantic_rules_current_definition", "semantic_rules", type_="foreignkey")
    op.drop_index(
        "uq_semantic_rule_definitions_rule_version", table_name="semantic_rule_definitions"
    )
    op.drop_index(
        "uq_semantic_rule_definitions_legacy_iri_version", table_name="semantic_rule_definitions"
    )
    op.drop_index(
        "ix_semantic_rule_definitions_semantic_rule_id", table_name="semantic_rule_definitions"
    )
    op.drop_constraint(
        "fk_semantic_rule_definitions_rule", "semantic_rule_definitions", type_="foreignkey"
    )
    op.drop_column("semantic_rule_definitions", "definition_hash")
    op.drop_column("semantic_rule_definitions", "semantic_rule_id")
    op.create_unique_constraint(
        "uq_semantic_rule_definitions_iri_version",
        "semantic_rule_definitions",
        ["rule_iri", "version"],
    )
    op.drop_table("semantic_rules")
    op.drop_table("ontology_write_fences")
    op.drop_table("modeling_attempt_item_results")
    op.drop_table("modeling_batch_attempts")
    op.drop_table("modeling_items")
    op.drop_table("modeling_batches")
