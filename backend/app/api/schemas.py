from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

    @field_validator("enum_values", mode="before")
    @classmethod
    def default_enum_values(cls, value: list[str] | None) -> list[str]:
        return value or []

    @field_validator("constraints", "external_mappings", mode="before")
    @classmethod
    def default_json_object(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        return value or {}


class RelationTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    parent_relation_type_id: str | None = None
    source_class_id: str
    target_class_id: str
    inverse_name: str | None = None
    scope_policy: Literal["schema_allowed", "entity_only", "both"] = "both"
    symmetric: bool = False
    transitive: bool = False
    status: str = "active"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    external_mappings: dict[str, Any] = Field(default_factory=dict)


class RelationTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    aliases: list[str] | None = None
    parent_relation_type_id: str | None = None
    source_class_id: str | None = None
    target_class_id: str | None = None
    inverse_name: str | None = None
    scope_policy: Literal["schema_allowed", "entity_only", "both"] | None = None
    symmetric: bool | None = None
    transitive: bool | None = None
    status: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
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
    scope_policy: str
    symmetric: bool
    transitive: bool
    status: str
    valid_from: datetime | None
    valid_to: datetime | None
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
    scope: Literal["instance"] = "instance"
    status: str = "active"
    valid_from: str | None = None
    valid_to: str | None = None


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
    scope: str = "instance"
    status: str = "active"
    valid_from: str | None = None
    valid_to: str | None = None


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


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_type: str = Field(min_length=1, max_length=80)
    owner: str | None = None
    authority_level: str = "unknown"
    status: str = "available"
    description: str | None = None
    connection_policy: dict[str, Any] = Field(default_factory=dict)


class DataSourceRead(DataSourceCreate):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_type: str | None = Field(default=None, min_length=1, max_length=80)
    owner: str | None = None
    authority_level: str | None = None
    status: str | None = None
    description: str | None = None
    connection_policy: dict[str, Any] | None = None


class DataResourceCreate(BaseModel):
    data_source_id: str
    name: str = Field(min_length=1, max_length=200)
    resource_type: str = "table"
    owner: str | None = None
    authority_level: str = "unknown"
    status: str = "available"
    description: str | None = None


class DataResourceRead(DataResourceCreate):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DataResourceUpdate(BaseModel):
    data_source_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    resource_type: str | None = None
    owner: str | None = None
    authority_level: str | None = None
    status: str | None = None
    description: str | None = None


class ExternalFieldCreate(BaseModel):
    data_resource_id: str
    name: str = Field(min_length=1, max_length=200)
    data_type: str = "string"
    sensitivity: Literal["public", "internal", "confidential", "restricted"] = "public"
    access_policy: Literal["allow", "mask", "approval_required", "deny"] = "allow"
    masking_rule: str | None = None
    approval_note: str | None = None
    audit_required: bool = False
    description: str | None = None


class ExternalFieldRead(ExternalFieldCreate):
    id: str
    project_id: str
    data_source_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalFieldUpdate(BaseModel):
    data_resource_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    data_type: str | None = None
    sensitivity: Literal["public", "internal", "confidential", "restricted"] | None = None
    access_policy: Literal["allow", "mask", "approval_required", "deny"] | None = None
    masking_rule: str | None = None
    approval_note: str | None = None
    audit_required: bool | None = None
    description: str | None = None


class SemanticMappingCreate(BaseModel):
    ontology_id: str
    ontology_version_id: str | None = None
    target_type: Literal["class", "property", "relation_type", "entity"]
    target_id: str
    field_id: str
    join_key: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    owner: str | None = None
    status: str = "active"


class SemanticMappingRead(SemanticMappingCreate):
    id: str
    project_id: str
    data_source_id: str
    resource_id: str
    external_resource_name: str
    external_field_name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SemanticMappingUpdate(BaseModel):
    ontology_version_id: str | None = None
    target_type: Literal["class", "property", "relation_type", "entity"] | None = None
    target_id: str | None = None
    field_id: str | None = None
    join_key: dict[str, Any] | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    owner: str | None = None
    status: str | None = None


class ConnectorTemplateCreate(BaseModel):
    data_source_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    allowed_field_ids: list[str] = Field(default_factory=list)
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    result_schema: dict[str, Any] = Field(default_factory=dict)
    access_policy: Literal["allow", "approval_required", "deny"] = "allow"


class ConnectorTemplateRead(ConnectorTemplateCreate):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConnectorTemplateUpdate(BaseModel):
    data_source_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    allowed_field_ids: list[str] | None = None
    parameter_schema: dict[str, Any] | None = None
    result_schema: dict[str, Any] | None = None
    access_policy: Literal["allow", "approval_required", "deny"] | None = None


class ConnectorQueryRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = None
    approved: bool = False


class ConnectorQueryResult(BaseModel):
    template_id: str
    authorized: bool
    denial_reason: str | None = None
    source: dict[str, Any]
    queried_at: datetime
    audit: dict[str, Any]
    rows: list[dict[str, Any]] = Field(default_factory=list)


class IdentifierResolutionRequest(BaseModel):
    left_values: list[str]
    right_values: list[str]


class IdentifierResolutionStats(BaseModel):
    left_count: int
    right_count: int
    overlap_count: int
    left_coverage: float
    right_coverage: float
    one_to_one: bool
    unmapped_left: list[str]
    unmapped_right: list[str]


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
    publication_report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    published_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EvidenceCreate(BaseModel):
    source_type: Literal["document", "conversation", "user_statement", "system"]
    artifact_id: str | None = None
    document_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    chunk_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    quote: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def sync_artifact_alias(self) -> "EvidenceCreate":
        if self.document_id is None and self.artifact_id is not None:
            self.document_id = self.artifact_id
        if self.artifact_id is None and self.document_id is not None:
            self.artifact_id = self.document_id
        return self


class EvidenceChunkRead(BaseModel):
    id: str
    artifact_id: str | None = None
    document_id: str
    sequence: int
    parse_revision: int
    page_number: int | None
    char_start: int
    char_end: int
    text: str
    content_hash: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_artifact_alias(self) -> "EvidenceChunkRead":
        if self.artifact_id is None:
            self.artifact_id = self.document_id
        return self


class EvidenceArtifactRead(BaseModel):
    id: str
    artifact_id: str | None = None
    project_id: str
    filename: str
    media_type: str
    size_bytes: int
    content_hash: str
    parse_status: str
    parse_error: str | None
    parser_version: str
    parse_count: int
    parse_revision: int
    reused: bool = False
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_artifact_alias(self) -> "EvidenceArtifactRead":
        if self.artifact_id is None:
            self.artifact_id = self.id
        return self


class KnowledgeConflictRead(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    proposal_id: str
    item_key: str
    field: str
    existing_value: Any
    proposed_value: Any
    status: str
    resolution: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConflictResolutionCreate(BaseModel):
    action: Literal["keep_existing", "accept_proposed", "manual"]
    value: Any | None = None
    reviewer_id: str | None = None


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
        "schema_change", "entity", "relation", "merge", "constraint", "rule"
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
    conflicts: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReviewDecisionCreate(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer_type: Literal["user", "service"] = "user"
    reviewer_id: str | None = None
    reason: str | None = None


class ProposalItemReview(BaseModel):
    action: Literal["approved", "rejected", "edited", "merged"]
    reviewer_type: Literal["user", "service"] = "user"
    reviewer_id: str | None = None
    reason: str | None = None
    data: dict[str, Any] | None = None
    merge_into_key: str | None = None


class ProposalBatchReview(BaseModel):
    item_keys: list[str] = Field(min_length=1)
    action: Literal["approved", "rejected"]
    reviewer_type: Literal["user", "service"] = "user"
    reviewer_id: str | None = None
    reason: str | None = None


class ReviewBatchRead(BaseModel):
    id: str
    stable_key: str
    project_id: str
    ontology_id: str
    ontology_version_id: str
    review_type: str
    status: str
    item_ids: list[str]
    counts: dict[str, Any]
    deep_link: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VersionDiffRead(BaseModel):
    from_version_id: str
    to_version_id: str
    schema_diff: dict[str, Any] = Field(alias="schema")
    graph: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True)


class InterviewAnswerCreate(BaseModel):
    answer: str = Field(min_length=1, max_length=20000)
    source_type: Literal["conversation", "user_statement"] = "conversation"
    actor_id: str | None = Field(default=None, max_length=255)


class InterviewAnswerRead(InterviewAnswerCreate):
    id: str
    project_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectBriefUpdate(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    confirmed_fields: list[str] = Field(default_factory=list)
    skipped_fields: list[str] = Field(default_factory=list)
    source_answer_ids: dict[str, list[str]] = Field(default_factory=dict)


class ProjectBriefRead(BaseModel):
    id: str | None = None
    project_id: str
    fields: dict[str, Any]
    field_states: dict[str, str]
    field_sources: dict[str, list[str]]
    missing_fields: list[str]
    clarification_items: list[dict[str, str]]
    completeness: float


class CompetencyQuestionCreate(BaseModel):
    ontology_id: str
    question: str = Field(min_length=1, max_length=4000)
    importance: int = Field(default=3, ge=1, le=5)
    position: int | None = Field(default=None, ge=0)
    query_definition: dict[str, Any] = Field(default_factory=dict)
    source_answer_ids: list[str] = Field(default_factory=list)
    source_brief_fields: list[str] = Field(default_factory=list)


class CompetencyQuestionUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=4000)
    importance: int | None = Field(default=None, ge=1, le=5)
    position: int | None = Field(default=None, ge=0)
    query_definition: dict[str, Any] | None = None
    source_answer_ids: list[str] | None = None
    source_brief_fields: list[str] | None = None
    active: bool | None = None


class CompetencyQuestionStatusUpdate(BaseModel):
    status: Literal["approved", "testable", "passed", "failed"]
    validation_result: dict[str, Any] = Field(default_factory=dict)


class CompetencyQuestionRead(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    question: str
    importance: int
    position: int
    status: str
    active: bool
    query_definition: dict[str, Any]
    validation_result: dict[str, Any]
    source_answer_ids: list[str]
    source_brief_fields: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FactClaimRead(BaseModel):
    id: str
    claim_key: str
    project_id: str
    ontology_id: str
    ontology_version_id: str
    claim_type: str
    layer: str
    subject: dict[str, Any]
    predicate: str
    value: Any
    anchor: dict[str, Any]
    graph_path: list[dict[str, Any]]
    evidence_ids: list[str]
    generation_reason: str
    confidence: float
    sensitivity: str
    access_policy: dict[str, Any]
    override_of_claim_id: str | None
    audit_status: str
    review_decision: dict[str, Any]
    linked_fix_proposal_id: str | None
    stale: bool
    stale_reason: str | None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EntityKnowledgeItemRead(BaseModel):
    source_type: str
    claim_id: str | None = None
    predicate: str
    value: Any
    anchor: dict[str, Any] = Field(default_factory=dict)
    layer: str | None = None
    audit_status: str | None = None
    confidence: float | None = None
    sensitivity: str | None = None
    access_policy: dict[str, Any] = Field(default_factory=dict)
    access_decision: str | None = None
    redacted: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    generation_reason: str | None = None
    relation_id: str | None = None
    rule_id: str | None = None
    inherited_from_class_id: str | None = None
    overrides: str | None = None
    overridden: bool = False


class EntityKnowledgeRuleRead(BaseModel):
    id: str
    rule_type: str
    scope: dict[str, Any]
    condition: dict[str, Any]
    conclusion: dict[str, Any]
    status: str
    priority: int
    evidence_ids: list[str]
    version: int


class EntityKnowledgeContextRead(BaseModel):
    entity: EntityRead
    class_chain: list[ClassRead]
    relation_ids: list[str]
    properties: list[EntityKnowledgeItemRead]
    entity_assertions: list[EntityKnowledgeItemRead]
    inherited_class_assertions: list[EntityKnowledgeItemRead]
    relation_assertions: list[EntityKnowledgeItemRead]
    rule_assertions: list[EntityKnowledgeItemRead]
    rules: list[EntityKnowledgeRuleRead]


class AssertionCreate(BaseModel):
    anchor: dict[str, Any]
    subject: dict[str, Any]
    predicate: str = Field(min_length=1, max_length=255)
    value: Any
    evidence_ids: list[str] = Field(default_factory=list)
    generation_reason: str = "direct_user_statement"
    claim_type: str = "direct"
    layer: str | None = None
    graph_path: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    sensitivity: str = "normal"
    access_policy: dict[str, Any] = Field(default_factory=dict)
    override_of_claim_id: str | None = None


class UnanchoredKnowledgeCreate(BaseModel):
    text: str = Field(min_length=1)
    source: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    embedding: list[float] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability: str | None = None


class UnanchoredKnowledgeRead(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    ontology_version_id: str
    text: str
    source: dict[str, Any]
    summary: str | None
    embedding: list[float]
    tags: list[str]
    confidence: float
    applicability: str | None
    status: str
    promoted_proposal_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackgroundRecallCreate(BaseModel):
    query: str | None = None
    query_embedding: list[float] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=50)


class BackgroundKnowledgePromotionCreate(BaseModel):
    proposal: ProposalCreate


class BackgroundKnowledgePromotionRead(BaseModel):
    knowledge: UnanchoredKnowledgeRead
    proposal: ProposalRead


class RuleDefinitionCreate(BaseModel):
    rule_type: Literal["classification", "derived_relation", "validation", "workflow"]
    scope: dict[str, Any] = Field(default_factory=dict)
    condition: dict[str, Any] = Field(default_factory=dict)
    conclusion: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    status: Literal["draft", "active", "deprecated"] = "active"
    evidence_ids: list[str] = Field(default_factory=list)
    created_from_proposal_id: str | None = None
    version: int = Field(default=1, ge=1)


class RuleDefinitionRead(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    ontology_version_id: str
    rule_type: str
    scope: dict[str, Any]
    condition: dict[str, Any]
    conclusion: dict[str, Any]
    priority: int
    status: str
    evidence_ids: list[str]
    created_from_proposal_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EntityKnowledgeRecallCreate(BaseModel):
    entity: dict[str, Any]
    background_query: str | None = None
    authorized: bool = False


class FactClaimReviewCreate(BaseModel):
    decision: Literal["approved", "rejected", "needs_correction"]
    reviewer_id: str | None = None
    reason: str | None = None
    linked_fix_proposal_id: str | None = None


class FactClaimSampleCreate(BaseModel):
    config: dict[str, int] = Field(default_factory=dict)


class PublicationReadinessRead(BaseModel):
    version_id: str
    ready: bool
    gates: list[dict[str, Any]]
    blocking: list[str]
    warnings: list[str]


class PublicationConfirm(BaseModel):
    confirm: bool
