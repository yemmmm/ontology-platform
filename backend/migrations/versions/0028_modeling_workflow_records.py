"""add versioned modeling workflow artifacts and execution events

Revision ID: 0028_modeling_workflow_records
Revises: 0027_r008_auth
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_modeling_workflow_records"
down_revision: str | None = "0027_r008_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "modeling_workflow_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("build_session_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36)),
        sa.Column("artifact_key", sa.String(255), nullable=False),
        sa.Column("client_version_id", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("content_format", sa.String(16), nullable=False),
        sa.Column("content", JSON, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_by_role", sa.String(64), nullable=False),
        sa.Column("workflow_name", sa.String(120), nullable=False),
        sa.Column("workflow_version", sa.String(120), nullable=False),
        sa.Column("role_prompt_version", sa.String(120)),
        sa.Column("supersedes_workflow_artifact_id", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "artifact_type IN ('business_knowledge_pack','modeling_coverage_matrix',"
            "'modeling_draft','review_report','verification_report')",
            name="ck_modeling_workflow_artifacts_type",
        ),
        sa.CheckConstraint(
            "content_format IN ('json','markdown')",
            name="ck_modeling_workflow_artifacts_format",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["build_session_id"], ["build_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supersedes_workflow_artifact_id"],
            ["modeling_workflow_artifacts.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "build_session_id",
            "client_version_id",
            name="uq_modeling_workflow_artifacts_session_client",
        ),
        sa.UniqueConstraint(
            "build_session_id",
            "artifact_key",
            "version",
            name="uq_modeling_workflow_artifacts_session_key_version",
        ),
    )
    op.create_index(
        "ix_modeling_workflow_artifacts_session_key_version",
        "modeling_workflow_artifacts",
        ["build_session_id", "artifact_key", "version"],
    )
    op.create_index(
        "ix_modeling_workflow_artifacts_ontology",
        "modeling_workflow_artifacts",
        ["ontology_id"],
    )

    op.create_table(
        "modeling_execution_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("build_session_id", sa.String(36), nullable=False),
        sa.Column("ontology_id", sa.String(36)),
        sa.Column("client_event_id", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("workflow_name", sa.String(120), nullable=False),
        sa.Column("workflow_version", sa.String(120), nullable=False),
        sa.Column("phase", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("report_source", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=False),
        sa.Column("role_prompt_version", sa.String(120)),
        sa.Column("agent_runtime", sa.String(120)),
        sa.Column("agent_model", sa.String(120)),
        sa.Column("reasoning_effort", sa.String(40)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "input_workflow_artifact_ids",
            JSON,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "output_workflow_artifact_ids",
            JSON,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("question_id", sa.String(255)),
        sa.Column("question_state", sa.String(32)),
        sa.Column("question_text", sa.Text()),
        sa.Column("answer_text", sa.Text()),
        sa.Column("answer_reason", sa.Text()),
        sa.Column("expected_question_head_event_id", sa.String(36)),
        sa.Column("interview_answer_id", sa.String(36)),
        sa.Column("decisions", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "rejected_alternatives", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("unresolved_items", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("blockers", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("next_step", sa.Text()),
        sa.Column("related_resources", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("quality_issues", JSON, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("token_usage", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("cost_summary", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("supersedes_execution_event_id", sa.String(36)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "report_source IN ('agent_reported','user_reported','platform_observed')",
            name="ck_modeling_execution_events_report_source",
        ),
        sa.CheckConstraint(
            "question_state IS NULL OR question_state IN "
            "('open','answered','skipped','uncertain','reopened')",
            name="ck_modeling_execution_events_question_state",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["build_session_id"], ["build_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_id"], ["ontologies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supersedes_execution_event_id"],
            ["modeling_execution_events.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "build_session_id",
            "client_event_id",
            name="uq_modeling_execution_events_session_client",
        ),
        sa.UniqueConstraint(
            "build_session_id", "sequence", name="uq_modeling_execution_events_session_sequence"
        ),
    )
    for name, columns in (
        ("ix_modeling_execution_events_session_sequence", ["build_session_id", "sequence"]),
        ("ix_modeling_execution_events_session_phase", ["build_session_id", "phase"]),
        ("ix_modeling_execution_events_session_type", ["build_session_id", "event_type"]),
        ("ix_modeling_execution_events_question", ["build_session_id", "question_id"]),
        ("ix_modeling_execution_events_ontology", ["ontology_id"]),
    ):
        op.create_index(name, "modeling_execution_events", columns)


def downgrade() -> None:
    op.drop_table("modeling_execution_events")
    op.drop_table("modeling_workflow_artifacts")
