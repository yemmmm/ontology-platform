from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.ontology import PropertyType


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    external_mappings: dict[str, Any] = Field(default_factory=dict)


class OntologyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    external_mappings: dict[str, Any] | None = None


class OntologyRead(BaseModel):
    id: str
    project_id: str
    current_version_id: str | None
    name: str
    description: str | None
    status: str
    external_mappings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    parent_class_ids: list[str] = Field(default_factory=list)
    external_mappings: dict[str, Any] = Field(default_factory=dict)


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    aliases: list[str] | None = None
    parent_class_ids: list[str] | None = None
    external_mappings: dict[str, Any] | None = None


class ClassRead(BaseModel):
    id: str
    ontology_id: str
    name: str
    normalized_label: str
    description: str | None
    aliases: list[str]
    parent_class_ids: list[str]
    external_mappings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClassSchemaRead(ClassRead):
    properties: list["PropertyDefRead"]


class PropertyDefCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: PropertyType
    description: str | None = None
    required: bool = False
    multi_valued: bool = False
    enum_values: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    external_mappings: dict[str, Any] = Field(default_factory=dict)


class PropertyDefUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: PropertyType | None = None
    description: str | None = None
    required: bool | None = None
    multi_valued: bool | None = None
    enum_values: list[str] | None = None
    constraints: dict[str, Any] | None = None
    external_mappings: dict[str, Any] | None = None


class PropertyDefRead(BaseModel):
    id: str
    class_id: str
    name: str
    type: str
    description: str | None
    required: bool
    multi_valued: bool
    enum_values: list[str]
    constraints: dict[str, Any]
    external_mappings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RelationTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    parent_relation_type_id: str | None = None
    source_class_id: str
    target_class_id: str
    inverse_name: str | None = None
    external_mappings: dict[str, Any] = Field(default_factory=dict)


class RelationTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    aliases: list[str] | None = None
    parent_relation_type_id: str | None = None
    source_class_id: str | None = None
    target_class_id: str | None = None
    inverse_name: str | None = None
    external_mappings: dict[str, Any] | None = None


class RelationTypeRead(BaseModel):
    id: str
    ontology_id: str
    name: str
    description: str | None
    aliases: list[str]
    parent_relation_type_id: str | None
    source_class_id: str
    target_class_id: str
    inverse_name: str | None
    normalized_type: str
    external_mappings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologySchemaRead(OntologyRead):
    classes: list[ClassSchemaRead]
    relation_types: list[RelationTypeRead]


class EntityCreate(BaseModel):
    class_id: str
    name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    ontology_version_id: str | None = None


class EntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    aliases: list[str] | None = None
    properties: dict[str, Any] | None = None
    ontology_version_id: str | None = None


class EntityRead(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    ontology_version_id: str | None = None
    class_id: str
    class_label: str
    name: str
    aliases: list[str]
    properties: dict[str, Any]


class RelationCreate(BaseModel):
    relation_type_id: str
    source_entity_id: str
    target_entity_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    ontology_version_id: str | None = None


class RelationRead(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    ontology_version_id: str | None = None
    relation_type_id: str
    relation_type: str
    source_entity_id: str
    target_entity_id: str
    properties: dict[str, Any]


class EntityWithRelationsRead(EntityRead):
    outgoing: list[RelationRead] = Field(default_factory=list)
    incoming: list[RelationRead] = Field(default_factory=list)


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class EntitySearchHit(EntityRead):
    score: float
    match_source: Literal["text", "vector", "hybrid"]


class EntitySearchResult(BaseModel):
    results: list[EntitySearchHit]
    count: int


class RelatedEntityRead(BaseModel):
    entity: EntityRead
    relations: list[RelationRead] = Field(default_factory=list)


class EntityExplainRead(BaseModel):
    entity: EntityRead
    class_schema: ClassSchemaRead | None = None
    direct_relations: list[RelationRead] = Field(default_factory=list)
    related_entities: list[RelatedEntityRead] = Field(default_factory=list)
    explain_text: str


class OntologyExportRead(BaseModel):
    ontology: OntologyRead
    classes: list[ClassSchemaRead]
    relation_types: list[RelationTypeRead]
    entities: list[EntityRead]
    relations: list[RelationRead]


class OntologyImportPayload(BaseModel):
    ontology: OntologyCreate
    classes: list[dict[str, Any]] = Field(default_factory=list)
    relation_types: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class AgentTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ontology_id: str
    question: str = Field(min_length=1, max_length=4000)


class AgentTestResponse(BaseModel):
    answer: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    graph_context: dict[str, Any] = Field(default_factory=dict)
    prompt_preview: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class OntologyVersionCreate(BaseModel):
    parent_version_id: str | None = None


class OntologyVersionRead(BaseModel):
    id: str
    ontology_id: str
    parent_version_id: str | None
    version_number: int
    status: str
    workflow_status: str
    schema_snapshot: dict[str, Any]
    graph_snapshot: dict[str, Any]
    created_at: datetime
    published_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EvidenceCreate(BaseModel):
    source_type: Literal["document", "conversation", "user_statement", "system"]
    document_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    chunk_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    quote: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)


class EvidenceRead(EvidenceCreate):
    id: str
    proposal_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalCreate(BaseModel):
    project_id: str
    ontology_id: str
    target_version_id: str
    proposal_type: Literal[
        "schema_change", "entity", "relation", "merge", "constraint"
    ]
    source_type: str = Field(min_length=1, max_length=40)
    idempotency_key: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any]
    created_by_type: Literal["agent", "user", "system"]
    created_by: str | None = None
    model_identifier: str | None = None
    prompt_version: str | None = None
    evidence: list[EvidenceCreate] = Field(default_factory=list)


class ProposalRead(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    target_version_id: str
    proposal_type: str
    status: str
    source_type: str
    idempotency_key: str
    payload: dict[str, Any]
    created_by_type: str
    created_by: str | None
    model_identifier: str | None
    prompt_version: str | None
    validation_result: dict[str, Any]
    review_result: dict[str, Any]
    application_result: dict[str, Any]
    audit_log: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None
    evidence: list[EvidenceRead] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    validation_runs: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReviewDecisionCreate(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer_type: Literal["user", "service"] = "user"
    reviewer_id: str | None = None
    reason: str | None = None


class VersionDiffRead(BaseModel):
    from_version_id: str
    to_version_id: str
    schema_diff: dict[str, Any] = Field(alias="schema")
    graph: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True)
