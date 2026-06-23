from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.repositories.postgres import Base


class OntologyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ConstraintSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


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
    current_version_id: Mapped[str | None] = mapped_column(String(36))
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
    versions: Mapped[list["OntologyVersionModel"]] = relationship(
        back_populates="ontology",
        cascade="all, delete-orphan",
        foreign_keys="OntologyVersionModel.ontology_id",
    )
    classes: Mapped[list["ClassModel"]] = relationship(
        back_populates="ontology",
        cascade="all, delete-orphan",
    )
    relation_types: Mapped[list["RelationTypeModel"]] = relationship(
        back_populates="ontology",
        cascade="all, delete-orphan",
        foreign_keys="RelationTypeModel.ontology_id",
    )
    constraints: Mapped[list["ConstraintModel"]] = relationship(
        back_populates="ontology",
        cascade="all, delete-orphan",
    )


class OntologyVersionModel(Base):
    __tablename__ = "ontology_versions"
    __table_args__ = (
        UniqueConstraint("ontology_id", "version_number", name="uq_ontology_versions_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="SET NULL")
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), default=VersionStatus.DRAFT.value, nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(32), default="gathering", nullable=False)
    schema_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    graph_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    ontology: Mapped[OntologyModel] = relationship(
        back_populates="versions",
        foreign_keys=[ontology_id],
    )
    parent_version: Mapped["OntologyVersionModel | None"] = relationship(
        remote_side=[id],
        foreign_keys=[parent_version_id],
    )


class ClassModel(Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("ontology_id", "name", name="uq_classes_ontology_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    parent_class_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
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

    ontology: Mapped[OntologyModel] = relationship(back_populates="classes")
    properties: Mapped[list["PropertyDefModel"]] = relationship(
        back_populates="class_",
        cascade="all, delete-orphan",
    )


class PropertyDefModel(Base):
    __tablename__ = "property_defs"
    __table_args__ = (UniqueConstraint("class_id", "name", name="uq_property_defs_class_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    multi_valued: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enum_values: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
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

    class_: Mapped[ClassModel] = relationship(back_populates="properties")


class RelationTypeModel(Base):
    __tablename__ = "relation_types"
    __table_args__ = (
        UniqueConstraint(
            "ontology_id",
            "name",
            "source_class_id",
            "target_class_id",
            name="uq_relation_types_ontology_name_source_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    parent_relation_type_id: Mapped[str | None] = mapped_column(
        ForeignKey("relation_types.id", ondelete="SET NULL"),
    )
    source_class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"), nullable=False)
    target_class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"), nullable=False)
    inverse_name: Mapped[str | None] = mapped_column(String(200))
    normalized_type: Mapped[str] = mapped_column(String(200), nullable=False)
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

    ontology: Mapped[OntologyModel] = relationship(
        back_populates="relation_types",
        foreign_keys=[ontology_id],
    )
    parent_relation_type: Mapped["RelationTypeModel | None"] = relationship(remote_side=[id])


class ConstraintModel(Base):
    __tablename__ = "constraints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32),
        default=ConstraintSeverity.ERROR.value,
        nullable=False,
    )
    expression: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
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

    ontology: Mapped[OntologyModel] = relationship(back_populates="constraints")


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


class SourceDocumentModel(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "content_hash", name="uq_source_documents_content"),
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


class SourceChunkModel(Base):
    __tablename__ = "source_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "parse_revision", "sequence", name="uq_source_chunks_sequence"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False
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


class KnowledgeConflictModel(Base):
    __tablename__ = "knowledge_conflicts"
    __table_args__ = (
        UniqueConstraint("proposal_id", "item_key", "field", name="uq_knowledge_conflict_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"), nullable=False
    )
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False
    )
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    field: Mapped[str] = mapped_column(String(255), nullable=False)
    existing_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    proposed_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    resolution: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProposalModel(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_proposals_project_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    ontology_id: Mapped[str] = mapped_column(ForeignKey("ontologies.id", ondelete="CASCADE"))
    target_version_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    proposal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))
    model_identifier: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(255))
    validation_result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    review_result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    application_result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    audit_log: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewBatchModel(Base):
    __tablename__ = "review_batches"
    __table_args__ = (UniqueConstraint("stable_key", name="uq_review_batches_stable_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stable_key: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    ontology_id: Mapped[str] = mapped_column(ForeignKey("ontologies.id", ondelete="CASCADE"))
    ontology_version_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="CASCADE")
    )
    review_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    item_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EvidenceModel(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(36))
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_id: Mapped[str | None] = mapped_column(String(100))
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewDecisionModel(Base):
    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ValidationRunModel(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublicationGateModel(Base):
    __tablename__ = "publication_gates"
    __table_args__ = (
        UniqueConstraint("ontology_version_id", "gate_type", name="uq_publication_gate_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_version_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    gate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FactClaimModel(Base):
    __tablename__ = "fact_claims"
    __table_args__ = (
        UniqueConstraint("ontology_version_id", "claim_key", name="uq_fact_claims_version_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_key: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"), nullable=False
    )
    ontology_version_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    layer: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    predicate: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    graph_path: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    generation_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(default=1.0, nullable=False)
    audit_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    review_decision: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    linked_fix_proposal_id: Mapped[str | None] = mapped_column(String(36))
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stale_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
