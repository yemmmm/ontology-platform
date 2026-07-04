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


class RelationTypeScope(StrEnum):
    SCHEMA_ALLOWED = "schema_allowed"
    ENTITY_ONLY = "entity_only"
    BOTH = "both"


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
    scope_policy: Mapped[str] = mapped_column(
        String(32),
        default=RelationTypeScope.BOTH.value,
        nullable=False,
    )
    symmetric: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    transitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


# Compatibility aliases for callers that still use the v0.3 source-document naming.
SourceDocumentModel = EvidenceArtifactModel
SourceChunkModel = EvidenceChunkModel


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
    anchor: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    graph_path: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    generation_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(default=1.0, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    access_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    override_of_claim_id: Mapped[str | None] = mapped_column(String(36))
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


class RuleDefinitionModel(Base):
    __tablename__ = "rule_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"), nullable=False
    )
    ontology_version_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    conclusion: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    created_from_proposal_id: Mapped[str | None] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UnanchoredKnowledgeModel(Base):
    __tablename__ = "unanchored_knowledge"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    ontology_id: Mapped[str] = mapped_column(
        ForeignKey("ontologies.id", ondelete="CASCADE"), nullable=False
    )
    ontology_version_id: Mapped[str] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(JSONB, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    applicability: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="background", nullable=False)
    promoted_proposal_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
    ontology_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="SET NULL")
    )
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
    source_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    reasoning_result_graph_iri: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    job_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
