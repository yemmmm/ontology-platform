from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.repositories.postgres import Base


class OntologyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ConstraintSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class RelationTypeScope(StrEnum):
    SCHEMA_ALLOWED = "schema_allowed"
    ENTITY_ONLY = "entity_only"
    BOTH = "both"


class BuildSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BuildCheckpointPhase(StrEnum):
    INTAKE = "intake"
    MODELING = "modeling"
    VERIFICATION = "verification"
    HANDOFF = "handoff"


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    ontologies: Mapped[list["OntologyModel"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class OntologyModel(Base):
    __tablename__ = "ontologies"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_ontologies_project_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=OntologyStatus.DRAFT.value, nullable=False)
    external_mappings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped[ProjectModel] = relationship(back_populates="ontologies")


class BuildSessionModel(Base):
    __tablename__ = "build_sessions"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "client_session_id", name="uq_build_sessions_project_client"
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_build_sessions_status",
        ),
        Index(
            "ix_build_sessions_project_status_activity",
            "project_id",
            "status",
            "last_activity_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    client_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    create_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("build_sessions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(32), default=BuildSessionStatus.ACTIVE.value, nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))
    last_resume_request_id: Mapped[str | None] = mapped_column(String(255))
    terminal_request_id: Mapped[str | None] = mapped_column(String(255))
    terminal_request_hash: Mapped[str | None] = mapped_column(String(64))
    completion_summary: Mapped[str | None] = mapped_column(Text)
    unresolved_items: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    checkpoints: Mapped[list["BuildCheckpointModel"]] = relationship(
        back_populates="build_session",
        cascade="all, delete-orphan",
        order_by="BuildCheckpointModel.sequence",
    )
    leases: Mapped[list["OntologyLeaseModel"]] = relationship(
        back_populates="build_session"
    )


class BuildCheckpointModel(Base):
    __tablename__ = "build_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "build_session_id",
            "client_checkpoint_id",
            name="uq_build_checkpoints_session_client",
        ),
        UniqueConstraint(
            "build_session_id", "sequence", name="uq_build_checkpoints_session_sequence"
        ),
        CheckConstraint(
            "phase IN ('intake', 'modeling', 'verification', 'handoff')",
            name="ck_build_checkpoints_phase",
        ),
        Index("ix_build_checkpoints_session_created", "build_session_id", "sequence"),
        Index("ix_build_checkpoints_ontology", "ontology_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    build_session_id: Mapped[str] = mapped_column(
        ForeignKey("build_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_checkpoint_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    ontology_id: Mapped[str | None] = mapped_column(
        ForeignKey("ontologies.id", ondelete="SET NULL")
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    current_step: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    blockers: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    related_batch_id: Mapped[str | None] = mapped_column(String(36))
    reported_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    build_session: Mapped[BuildSessionModel] = relationship(back_populates="checkpoints")


class OntologyLeaseModel(Base):
    __tablename__ = "ontology_leases"
    __table_args__ = (
        Index("ix_ontology_leases_session", "build_session_id"),
        Index("ix_ontology_leases_expiry", "expires_at"),
    )

    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    build_session_id: Mapped[str] = mapped_column(
        ForeignKey("build_sessions.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    acquired_by: Mapped[str | None] = mapped_column(String(255))
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_request_id: Mapped[str | None] = mapped_column(String(255))
    last_request_operation: Mapped[str | None] = mapped_column(String(32))
    last_request_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    build_session: Mapped[BuildSessionModel] = relationship(back_populates="leases")


class ApiKeyModel(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectBriefModel(Base):
    __tablename__ = "project_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    field_states: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    field_sources: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CompetencyQuestionModel(Base):
    __tablename__ = "competency_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    ontology_id: Mapped[str] = mapped_column(ForeignKey("ontologies.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_answer_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    source_brief_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    query_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    validation_result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InterviewAnswerModel(Base):
    __tablename__ = "interview_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="conversation", nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvidenceArtifactModel(Base):
    __tablename__ = "evidence_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "content_hash", name="uq_evidence_artifacts_content"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str] = mapped_column(String(40), default="v1", nullable=False)
    parse_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parse_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EvidenceChunkModel(Base):
    __tablename__ = "evidence_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "parse_revision", "sequence", name="uq_evidence_chunks_sequence"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    parse_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvidenceReferenceModel(Base):
    __tablename__ = "evidence_references"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "normalized_document_name",
            "excerpt_hash",
            name="uq_evidence_references_project_document_excerpt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvidenceAssociationModel(Base):
    __tablename__ = "evidence_associations"
    __table_args__ = (
        UniqueConstraint(
            "ontology_id",
            "target_type",
            "target_id",
            "evidence_reference_id",
            name="uq_evidence_associations_target_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    graph_set_id: Mapped[str | None] = mapped_column(String(36), index=True)
    evidence_reference_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_references.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    client_item_id: Mapped[str | None] = mapped_column(String(255))
    edit_audit_id: Mapped[str | None] = mapped_column(
        ForeignKey("semantic_edit_audits.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FactEvidenceBindingModel(Base):
    """Fact-level evidence binding stored in Postgres.

    Each row binds one piece of evidence (chunk reference or raw text) to a
    specific fact identified by fact_id (sha256(s,p,o,g)). Replaces the
    legacy RDF prov:wasDerivedFrom + chunk literal pattern.
    """

    __tablename__ = "fact_evidence_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fact_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_iri: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    predicate_iri: Mapped[str] = mapped_column(Text, nullable=False)
    object_value: Mapped[str] = mapped_column(Text, nullable=False)
    graph_iri: Mapped[str] = mapped_column(Text, nullable=False)

    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    evidence_reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_references.id", ondelete="SET NULL"), nullable=True, index=True
    )

    document_filename: Mapped[str | None] = mapped_column(String(255))
    sequence: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    actor: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Compatibility aliases for callers that still use the v0.3 source-document naming.
SourceDocumentModel = EvidenceArtifactModel
SourceChunkModel = EvidenceChunkModel



class DataSourceModel(Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_data_sources_project_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(200))
    authority_level: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="available", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    connection_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DataResourceModel(Base):
    __tablename__ = "data_resources"
    __table_args__ = (
        UniqueConstraint("data_source_id", "name", name="uq_data_resources_source_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    data_source_id: Mapped[str] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), default="table", nullable=False)
    owner: Mapped[str | None] = mapped_column(String(200))
    authority_level: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="available", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExternalFieldModel(Base):
    __tablename__ = "external_fields"
    __table_args__ = (
        UniqueConstraint("data_resource_id", "name", name="uq_external_fields_resource_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    data_source_id: Mapped[str] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    data_resource_id: Mapped[str] = mapped_column(
        ForeignKey("data_resources.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type: Mapped[str] = mapped_column(String(80), default="string", nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(40), default="public", nullable=False)
    access_policy: Mapped[str] = mapped_column(String(80), default="allow", nullable=False)
    masking_rule: Mapped[str | None] = mapped_column(String(200))
    approval_note: Mapped[str | None] = mapped_column(Text)
    audit_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SemanticMappingModel(Base):
    __tablename__ = "semantic_mappings"
    __table_args__ = (
        UniqueConstraint("ontology_id", "target_type", "target_id", "field_id", name="uq_semantic_mapping_target_field"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    ontology_id: Mapped[str] = mapped_column(ForeignKey("ontologies.id", ondelete="CASCADE"))
    # Stage 3: legacy ontology_versions table dropped; column retained as plain
    # string for backward-compatible reads until Stage 4 catalog rebuild removes
    # the SemanticMappingModel entirely. No FK constraint.
    ontology_version_id: Mapped[str | None] = mapped_column(String(36))
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    data_source_id: Mapped[str] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("data_resources.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[str] = mapped_column(
        ForeignKey("external_fields.id", ondelete="CASCADE"), nullable=False
    )
    external_resource_name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_field_name: Mapped[str] = mapped_column(String(200), nullable=False)
    join_key: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(default=1.0, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ConnectorTemplateModel(Base):
    __tablename__ = "connector_templates"
    __table_args__ = (
        UniqueConstraint("data_source_id", "name", name="uq_connector_templates_source_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    data_source_id: Mapped[str] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    allowed_field_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    parameter_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    access_policy: Mapped[str] = mapped_column(String(80), default="allow", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ConnectorQueryAuditModel(Base):
    __tablename__ = "connector_query_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    template_id: Mapped[str] = mapped_column(
        ForeignKey("connector_templates.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[str | None] = mapped_column(String(255))
    authorized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    denial_reason: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    queried_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SemanticGraphStateModel(Base):
    __tablename__ = "semantic_graph_states"
    __table_args__ = (UniqueConstraint("graph_iri", name="uq_semantic_graph_states_graph_iri"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_iri: Mapped[str] = mapped_column(Text, nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SemanticEditAuditModel(Base):
    __tablename__ = "semantic_edit_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    input_format: Mapped[str] = mapped_column(String(32), nullable=False)
    target_graph_iri: Mapped[str | None] = mapped_column(Text)
    affected_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    graph_delta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    evidence_status: Mapped[str | None] = mapped_column(String(64))
    warning_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SemanticValidationRunModel(Base):
    __tablename__ = "semantic_validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    shape_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    conforms: Mapped[bool | None] = mapped_column(Boolean)
    report_graph_iri: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticReasoningRunModel(Base):
    __tablename__ = "semantic_reasoning_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    result_graph_iri: Mapped[str | None] = mapped_column(Text)
    reasoner: Mapped[str] = mapped_column(String(255), default="command", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    consistent: Mapped[bool | None] = mapped_column(Boolean)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticProjectionJobModel(Base):
    __tablename__ = "semantic_projection_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_set_id: Mapped[str | None] = mapped_column(String(36))
    projection_kind: Mapped[str] = mapped_column(
        String(40), default="search", nullable=False
    )
    projection_version: Mapped[str] = mapped_column(
        String(80), default="v1", nullable=False
    )
    projection_scope: Mapped[str] = mapped_column(
        String(40), default="asserted", nullable=False
    )
    source_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    reasoning_result_graph_iri: Mapped[str | None] = mapped_column(Text)
    rule_result_graph_iri: Mapped[str | None] = mapped_column(Text)
    source_signature: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    input_graph_revisions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    input_derived_pointers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    target_store: Mapped[str | None] = mapped_column(String(80))
    target_partition: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    job_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticProjectionManifestModel(Base):
    __tablename__ = "semantic_projection_manifests"
    __table_args__ = (
        UniqueConstraint(
            "graph_set_id",
            "projection_kind",
            "target_partition",
            name="uq_semantic_projection_manifests_set_kind_partition",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_set_id: Mapped[str] = mapped_column(String(36), nullable=False)
    projection_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    active_job_id: Mapped[str | None] = mapped_column(String(36))
    source_signature: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    projection_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    target_partition: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="current", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    manifest_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class SemanticGraphRegistryModel(Base):
    __tablename__ = "semantic_graph_registry"
    __table_args__ = (
        UniqueConstraint("graph_iri", name="uq_semantic_graph_registry_graph_iri"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_iri: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    semantic_owner_type: Mapped[str | None] = mapped_column(String(40))
    semantic_owner_id: Mapped[str | None] = mapped_column(String(255))
    mutable_by_direct_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    managed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    registry_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticGraphRevisionModel(Base):
    __tablename__ = "semantic_graph_revisions"
    __table_args__ = (
        UniqueConstraint("graph_iri", name="uq_semantic_graph_revisions_graph_iri"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_iri: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    last_edit_audit_id: Mapped[str | None] = mapped_column(String(36))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    changed_by: Mapped[str | None] = mapped_column(String(255))
    revision_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticGraphSetModel(Base):
    __tablename__ = "semantic_graph_sets"
    __table_args__ = (
        Index(
            "uq_semantic_graph_sets_default_ontology",
            "scope_type",
            "scope_id",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_signature: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    graph_set_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    members: Mapped[list["SemanticGraphSetMemberModel"]] = relationship(
        back_populates="graph_set",
        cascade="all, delete-orphan",
        order_by="SemanticGraphSetMemberModel.sort_order",
    )


class SemanticGraphSetMemberModel(Base):
    __tablename__ = "semantic_graph_set_members"
    __table_args__ = (
        UniqueConstraint(
            "graph_set_id", "graph_iri", name="uq_semantic_graph_set_members_set_graph"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_set_id: Mapped[str] = mapped_column(
        ForeignKey("semantic_graph_sets.id", ondelete="CASCADE"), nullable=False
    )
    graph_iri: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    member_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    graph_set: Mapped[SemanticGraphSetModel] = relationship(back_populates="members")


class SemanticDerivedResultPointerModel(Base):
    __tablename__ = "semantic_derived_result_pointers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_set_id: Mapped[str | None] = mapped_column(String(36))
    result_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    result_graph_iri: Mapped[str] = mapped_column(Text, nullable=False)
    source_signature: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    engine_name: Mapped[str | None] = mapped_column(String(255))
    engine_version: Mapped[str | None] = mapped_column(String(255))
    rule_version: Mapped[str | None] = mapped_column(String(255))
    shape_version: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="current", nullable=False)
    became_current_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pointer_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SemanticGraphGcRunModel(Base):
    __tablename__ = "semantic_graph_gc_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    gc_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticRuleDefinitionModel(Base):
    __tablename__ = "semantic_rule_definitions"
    __table_args__ = (
        UniqueConstraint("rule_iri", "version", name="uq_semantic_rule_definitions_iri_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_iri: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_roles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    output_kind: Mapped[str] = mapped_column(String(40), default="assertion", nullable=False)
    uses_inferred_facts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    safety_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    rule_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticRuleRunModel(Base):
    __tablename__ = "semantic_rule_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_set_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rule_definition_id: Mapped[str | None] = mapped_column(String(36))
    rule_version: Mapped[str | None] = mapped_column(String(80))
    result_graph_iri: Mapped[str | None] = mapped_column(Text)
    rule_run_graph_iri: Mapped[str | None] = mapped_column(Text)
    engine_name: Mapped[str] = mapped_column(String(40), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(255))
    source_signature: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    generated_statement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class SemanticMigrationRunModel(Base):
    """Phase 7 canonical RDF dataset migration run.

    Each run records the scope, mode, source signature, and parity reports for
    one backfill / dual-write / cutover / rollback attempt. Runs are scoped by
    ontology version, project, catalog source, connector source, or globally.
    """

    __tablename__ = "semantic_migration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    phase2_mapping_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="phase2-v1"
    )
    source_snapshot_signature: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    target_graph_set_id: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    batches: Mapped[list["SemanticMigrationBatchModel"]] = relationship(
        back_populates="migration_run",
        cascade="all, delete-orphan",
        order_by="SemanticMigrationBatchModel.batch_index",
    )
    parity_reports: Mapped[list["SemanticMigrationParityReportModel"]] = relationship(
        back_populates="migration_run",
        cascade="all, delete-orphan",
        order_by="SemanticMigrationParityReportModel.created_at",
    )


class SemanticMigrationBatchModel(Base):
    """Phase 7 batch record for one migration run.

    A batch is the unit of idempotent rerun. Two batches with identical source
    hash and target hash for the same run are considered redundant and must not
    mutate the target graph set when re-applied.
    """

    __tablename__ = "semantic_migration_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    migration_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("semantic_migration_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_index: Mapped[int] = mapped_column(Integer, nullable=False)
    object_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    target_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    inserted_quad_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_quad_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_hash: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    batch_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    migration_run: Mapped[SemanticMigrationRunModel] = relationship(back_populates="batches")


class SemanticMigrationParityReportModel(Base):
    """Phase 7 parity check report comparing legacy and RDF-derived projections."""

    __tablename__ = "semantic_migration_parity_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    migration_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("semantic_migration_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    check_name: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    legacy_count: Mapped[int | None] = mapped_column(Integer)
    rdf_count: Mapped[int | None] = mapped_column(Integer)
    diff_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    sample_diffs: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    parity_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    migration_run: Mapped[SemanticMigrationRunModel] = relationship(back_populates="parity_reports")
