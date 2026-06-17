from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), default=OntologyStatus.DRAFT.value, nullable=False)
    schema_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    ontology: Mapped[OntologyModel] = relationship(
        back_populates="versions",
        foreign_keys=[ontology_id],
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
