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


class SemanticDatasetLoadRequest(BaseModel):
    content: str
    format: Literal["trig", "turtle", "json-ld"]
    base_iri: str | None = None


class SemanticDatasetLoadResponse(BaseModel):
    loaded: bool
    format: str
    graph_count: int | None = None
    triple_count: int | None = None
    warnings: list[str] = Field(default_factory=list)


class SemanticSparqlQueryRequest(BaseModel):
    query: str
    timeout_seconds: float | None = Field(default=None, gt=0)
    result_limit: int | None = Field(default=None, gt=0)


class SemanticSparqlQueryResponse(BaseModel):
    result: Any
    result_format: str
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)


class SemanticValidationRunRequest(BaseModel):
    data_graph_iris: list[str]
    shape_graph_iris: list[str]
    inference: str | None = None


class SemanticValidationRunResponse(BaseModel):
    run_id: str
    status: str
    conforms: bool | None = None
    report_text: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SemanticReasoningRunRequest(BaseModel):
    source_graph_iris: list[str]
    tasks: list[str] = Field(default_factory=lambda: ["consistency"])
    persist_result_graph: bool = False
    graph_set_id: str | None = None
    engine_version: str | None = None
    shape_version: str | None = None


class SemanticReasoningRunResponse(BaseModel):
    run_id: str
    status: str
    consistent: bool | None = None
    classification: dict[str, Any] = Field(default_factory=dict)
    entailments: list[dict[str, Any]] = Field(default_factory=list)
    result_graph_iri: str | None = None
    error: str | None = None
    derived_pointer: dict[str, Any] | None = None


class SemanticEditRequest(BaseModel):
    format: Literal["trig", "turtle", "json-ld", "sparql-update"]
    content: str
    target_graph_iri: str | None = None
    validate_edit: bool = Field(default=True, alias="validate")
    shape_graph_iris: list[str] = Field(default_factory=list)
    actor: str | None = None
    reason: str | None = None
    evidence_status: Literal["evidence_bound", "missing_evidence"] | None = None
    warning_state: dict[str, Any] = Field(default_factory=dict)


class SemanticEditResponse(BaseModel):
    audit_id: str
    applied: bool
    affected_graph_iris: list[str]
    delta: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    validation: dict[str, Any] | None = None
    graph_revisions: dict[str, int] = Field(default_factory=dict)
    stale_derived_pointers: list[dict[str, Any]] = Field(default_factory=list)


class SemanticEditAuditRead(BaseModel):
    id: str
    actor: str | None = None
    reason: str | None = None
    input_format: str
    target_graph_iri: str | None = None
    affected_graph_iris: list[str]
    validation_result: dict[str, Any] | None = None
    graph_delta: dict[str, Any]
    evidence_status: str | None = None
    warning_state: dict[str, Any]
    applied: bool
    created_at: datetime


class SemanticGraphEditabilityRequest(BaseModel):
    editable: bool
    actor: str | None = None
    reason: str | None = None


class SemanticGraphEditabilityResponse(BaseModel):
    graph_iri: str
    editable: bool
    updated_by: str | None = None
    reason: str | None = None


class SemanticProjectionRequest(BaseModel):
    source_graph_iris: list[str]
    reasoning_result_graph_iri: str | None = None


class SemanticProjectionResponse(BaseModel):
    job_id: str
    status: str
    node_count: int
    relationship_count: int
    error: str | None = None


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


class SemanticNamespaceRead(BaseModel):
    context: dict[str, Any]
    iri_patterns: dict[str, str]


class SemanticProjectionParseRequest(BaseModel):
    format: Literal["trig", "turtle", "json-ld"]
    content: str


class SemanticCompactProjectionRead(BaseModel):
    classes: list[dict[str, Any]]
    relation_types: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    fact_claims: list[dict[str, Any]]


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


class VersionMutabilityUpdate(BaseModel):
    mutable: bool


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


class SemanticGraphMember(BaseModel):
    graph_iri: str
    role: str
    required: bool = True
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticGraphRegistryCreate(BaseModel):
    graph_iri: str
    category: str
    owner_type: str | None = None
    owner_id: str | None = None
    mutable_by_direct_edit: bool | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticGraphRegistryRead(BaseModel):
    graph_iri: str
    category: str
    registered: bool
    owner_type: str | None = None
    owner_id: str | None = None
    mutable_by_direct_edit: bool | None = None
    editable: bool | None = None
    editability_reason: str | None = None
    revision: int | None = None
    content_hash: str | None = None
    derived_pointers: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticGraphRegistryListResponse(BaseModel):
    graphs: list[SemanticGraphRegistryRead]
    summary: dict[str, Any]


class SemanticGraphSetCreate(BaseModel):
    name: str
    scope_type: str
    scope_id: str | None = None
    members: list[SemanticGraphMember]
    created_by: str | None = None
    supersedes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticGraphSetMembershipUpdate(BaseModel):
    members: list[SemanticGraphMember]


class SemanticGraphSetRead(BaseModel):
    id: str
    name: str
    scope_type: str
    scope_id: str | None
    status: str
    source_signature: str
    created_by: str | None = None
    members: list[dict[str, Any]]
    current_pointers: list[dict[str, Any]]
    metadata: dict[str, Any]


class SemanticGraphSetListResponse(BaseModel):
    graph_sets: list[SemanticGraphSetRead]


class SemanticGraphSetReasoningRunRequest(BaseModel):
    tasks: list[str] = Field(default_factory=lambda: ["consistency"])
    persist_result_graph: bool = True
    engine_version: str | None = None
    shape_version: str | None = None


class SemanticDerivedResultReconcileResponse(BaseModel):
    graph_sets_inspected: int
    pointers_marked_current: int
    pointers_marked_stale: int


class SemanticGraphGcRequest(BaseModel):
    target_kind: Literal["reasoning_result"] = "reasoning_result"
    dry_run: bool = False
    retention_days: int | None = Field(default=None, ge=0)


class SemanticGraphGcResponse(BaseModel):
    gc_run_id: str
    target_kind: str
    status: str
    candidate_count: int
    deleted_count: int
    dry_run: bool
    deleted_graph_iris: list[str]
    errors: list[dict[str, Any]]


class SemanticGovernanceStatusResponse(BaseModel):
    graphs: dict[str, Any]
    derived: dict[str, Any]


# ---------------------------------------------------------------------------
# Phase 5: rule definitions, rule runs, graph-set validation, missing evidence
# ---------------------------------------------------------------------------


class SemanticRuleDefinitionCreate(BaseModel):
    rule_iri: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=255)
    language: Literal["sparql_construct", "platform_dsl", "workflow_state_machine"]
    body: dict[str, Any]
    input_roles: list[str] = Field(default_factory=list)
    output_kind: Literal["assertion", "validation", "workflow", "annotation"] = "assertion"
    uses_inferred_facts: bool = False
    requires_review: bool = False
    priority: int = 0
    safety_profile: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "active", "retired", "rejected"] = "draft"
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticRuleDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["draft", "active", "retired", "rejected"] | None = None
    priority: int | None = None
    metadata: dict[str, Any] | None = None


class SemanticRuleDefinitionRead(BaseModel):
    id: str
    rule_iri: str
    name: str
    language: str
    version: str
    status: str
    body: dict[str, Any]
    input_roles: list[str]
    output_kind: str
    uses_inferred_facts: bool
    requires_review: bool
    priority: int
    safety_profile: dict[str, Any]
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]


class SemanticRuleDefinitionListResponse(BaseModel):
    rules: list[SemanticRuleDefinitionRead]


class SemanticGraphSetValidationRunRequest(BaseModel):
    shape_graph_iris: list[str] = Field(default_factory=list)
    inference: str | None = None
    validation_scope: Literal["asserted_only", "asserted_plus_reasoning"] = "asserted_only"
    reasoning_result_graph_iri: str | None = None
    shape_version: str | None = None
    engine_version: str | None = None
    persist_report_graph: bool = True
    actor: str | None = None


class SemanticValidationRunRead(BaseModel):
    run_id: str
    status: str
    conforms: bool | None = None
    report_graph_iri: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    guidance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    graph_set_id: str | None = None
    source_signature: str = ""
    input_graph_revisions: dict[str, int] = Field(default_factory=dict)
    shape_version: str | None = None
    engine_version: str | None = None
    validation_scope: str = "asserted_only"
    missing_evidence_dependencies: dict[str, Any] = Field(default_factory=dict)
    staleness: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class SemanticGraphSetConstructRunRequest(BaseModel):
    template: str
    rule_definition_id: str | None = None
    rule_version: str | None = None
    engine_version: str | None = None
    promote_pointer: bool = True
    actor: str | None = None


class SemanticGraphSetRuleRunRequest(BaseModel):
    rule_definition_id: str | None = None
    rule_iri: str | None = None
    rule_definition_ids: list[str] | None = None
    engine_version: str | None = None
    promote_pointer: bool = True
    actor: str | None = None


class SemanticRuleRunRead(BaseModel):
    run_id: str
    status: str
    engine_name: str
    engine_version: str | None = None
    graph_set_id: str
    rule_definition_id: str | None = None
    rule_version: str | None = None
    result_graph_iri: str | None = None
    rule_run_graph_iri: str | None = None
    generated_statement_count: int = 0
    statements: list[dict[str, Any]] = Field(default_factory=list)
    bindings: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False
    missing_evidence_dependencies: dict[str, Any] = Field(default_factory=dict)
    audit_status: str = "system_accepted"
    explanations: list[dict[str, Any]] = Field(default_factory=list)
    rule_count: int | None = None
    derived_pointer: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class SemanticMissingEvidenceSummary(BaseModel):
    graph_set_id: str
    dependencies: list[dict[str, Any]]
    summary: dict[str, Any]
    warning: str | None = None


class SemanticReasoningRunRead(BaseModel):
    run_id: str
    status: str
    consistent: bool | None = None
    classification: dict[str, Any] = Field(default_factory=dict)
    entailments: list[dict[str, Any]] = Field(default_factory=list)
    result_graph_iri: str | None = None
    graph_set_id: str | None = None
    source_signature: str = ""
    input_graph_revisions: dict[str, int] = Field(default_factory=dict)
    input_derived_pointers: dict[str, Any] = Field(default_factory=dict)
    engine_version: str | None = None
    shape_version: str | None = None
    tasks: list[str] = Field(default_factory=list)
    profile: str = "owl2_dl"
    missing_evidence_dependencies: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    derived_pointer: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


# ----------------------------------------------------------------------------
# Phase 6 — graph-derived read models, exports, projection jobs/manifests
# ----------------------------------------------------------------------------


class SemanticReadModelEnvelope(BaseModel):
    graph_set_id: str
    source_signature: str
    projection_version: str
    model_name: str = ""
    include: str
    derived_state: dict[str, Any]
    warnings: list[dict[str, str]] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)


class SemanticStatementItem(BaseModel):
    id: str
    iri: str
    label: str | None = None
    source_graph_iri: str
    assertion_kind: str
    evidence_status: str
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: dict[str, Any]
    audit_status: str | None = None
    staleness: dict[str, Any]


class SemanticResourceRead(BaseModel):
    iri: str
    label: str | None = None
    graph_set_id: str | None = None
    source_signature: str | None = None
    assertion_kind: str
    evidence_status: str
    source_graph_iri: str
    properties: dict[str, Any] = Field(default_factory=dict)
    derived_state: dict[str, Any] = Field(default_factory=dict)
    warnings: list[dict[str, str]] = Field(default_factory=list)


class SemanticExportRequest(BaseModel):
    format: Literal["trig", "turtle", "json-ld"] = "trig"
    include: Literal[
        "asserted",
        "asserted-plus-reasoning",
        "asserted-plus-rules",
        "full-working-view",
    ] = "asserted"
    include_evidence: bool = False
    include_shapes: bool = False
    include_policy: bool = False
    include_metadata: bool = False
    allow_stale_derived: bool = False
    visibility_context: dict[str, Any] | None = None


class SemanticProjectionJobCreate(BaseModel):
    graph_set_id: str
    projection_kind: Literal[
        "business_json", "neo4j", "search", "vector", "export_cache"
    ]
    projection_version: str
    include: Literal[
        "asserted",
        "asserted-plus-reasoning",
        "asserted-plus-rules",
        "full-working-view",
    ] = "asserted"
    allow_stale_derived: bool = False
    mode: Literal["dry_run", "rebuild", "rebuild_side_by_side", "reconcile"] = "rebuild"
    target_partition: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticProjectionJobRead(BaseModel):
    id: str
    graph_set_id: str | None
    projection_kind: str
    projection_version: str
    projection_scope: str
    source_signature: str
    input_graph_revisions: dict[str, Any]
    input_derived_pointers: dict[str, Any]
    target_store: str | None
    target_partition: str | None
    status: str
    node_count: int
    relationship_count: int
    document_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SemanticProjectionJobListResponse(BaseModel):
    items: list[SemanticProjectionJobRead]
    total: int


class SemanticProjectionManifestRead(BaseModel):
    id: str
    graph_set_id: str
    projection_kind: str
    active_job_id: str | None
    source_signature: str
    projection_version: str
    target_partition: str
    status: str
    updated_at: datetime
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SemanticProjectionStatusResponse(BaseModel):
    manifests: list[SemanticProjectionManifestRead]
    stale: list[str]
    missing: list[str]


class SemanticProjectionReconcileResponse(BaseModel):
    reconciled: int
    marked_stale: list[str]
    warnings: list[dict[str, str]] = Field(default_factory=list)


# ----------------------------------------------------------------------------
# Phase 7 — canonical RDF dataset migration runs, batches, and parity reports
# ----------------------------------------------------------------------------


class SemanticMigrationPreflightRequest(BaseModel):
    scope_type: Literal[
        "project",
        "ontology",
        "version",
        "catalog_source",
        "connector_source",
        "global",
        "ad_hoc",
    ]
    scope_id: str | None = None
    target_graph_set_id: str | None = None


class SemanticMigrationPreflightResponse(BaseModel):
    scope_type: str
    scope_id: str | None
    ready: bool
    checks: list[dict[str, Any]]
    inventory: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class SemanticMigrationCreateRequest(BaseModel):
    scope_type: Literal[
        "project",
        "ontology",
        "version",
        "catalog_source",
        "connector_source",
        "global",
        "ad_hoc",
    ]
    scope_id: str | None = None
    mode: Literal["dry_run", "shadow", "dual_write_backfill", "cutover", "rollback"]
    target_graph_set_id: str | None = None
    batch_size: int | None = Field(default=None, ge=1, le=10_000)
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticMigrationBatchRead(BaseModel):
    id: str
    migration_run_id: str
    batch_index: int
    object_kind: str
    source_ids: list[str]
    target_graph_iris: list[str]
    status: str
    inserted_quad_count: int
    deleted_quad_count: int
    source_hash: str
    target_hash: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SemanticMigrationParityReportRead(BaseModel):
    id: str
    migration_run_id: str
    check_name: str
    scope_type: str
    scope_id: str | None
    status: str
    legacy_count: int | None
    rdf_count: int | None
    diff_summary: dict[str, Any]
    sample_diffs: list[Any]
    created_at: datetime
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SemanticMigrationRunRead(BaseModel):
    id: str
    scope_type: str
    scope_id: str | None
    mode: str
    status: str
    phase2_mapping_version: str
    source_snapshot_signature: str
    target_graph_set_id: str | None
    started_at: datetime
    finished_at: datetime | None
    created_by: str | None
    error: str | None
    metadata: dict[str, Any]
    batches: list[SemanticMigrationBatchRead] = Field(default_factory=list)
    parity_reports: list[SemanticMigrationParityReportRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SemanticMigrationRunListResponse(BaseModel):
    items: list[SemanticMigrationRunRead]
    total: int


class SemanticMigrationBatchRunResponse(BaseModel):
    run_id: str
    status: str
    batch: SemanticMigrationBatchRead | None = None
    applied: bool
    warnings: list[str] = Field(default_factory=list)


class SemanticMigrationParityCheckResponse(BaseModel):
    run_id: str
    status: str
    reports: list[SemanticMigrationParityReportRead]
    mandatory_passed: bool
    blocking_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SemanticMigrationCutoverResponse(BaseModel):
    run_id: str
    status: str
    previous_modes: dict[str, Any]
    new_modes: dict[str, Any]
    gates_passed: bool
    blocking_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SemanticMigrationRollbackResponse(BaseModel):
    run_id: str
    status: str
    restored_modes: dict[str, Any]
    rolled_back_graphs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _canonical_command_kinds() -> tuple[str, ...]:
    """Return the canonical command kinds supported by the compiler.

    Looked up at import time so the API schema stays in sync with the compiler
    registry (Stage 2 §3.3.1 added 19 new kinds). Falls back to a static list
    if the compiler module cannot be imported in this context.
    """
    try:
        from app.services.semantic_command_compiler import supported_command_kinds

        return tuple(supported_command_kinds())
    except Exception:  # pragma: no cover - defensive
        return (
            "create_class",
            "create_relation_type",
            "submit_assertion",
            "update_evidence_status",
        )


class SemanticCanonicalProductWriteRequest(BaseModel):
    """Phase 7 product command compiler entry point.

    Used to demonstrate that structured product APIs compile to the same canonical
    RDF graph delta as direct semantic edits. Each ``command_kind`` maps to a
    compiler that produces an :class:`RdfGraphDelta` for the canonical writer.
    """

    command_kind: Literal[_canonical_command_kinds()]  # type: ignore[valid-type]
    graph_set_id: str
    target_graph_iri: str | None = None
    payload: dict[str, Any]
    actor: str | None = None
    reason: str | None = None
    validate_edit: bool = True
    shape_graph_iris: list[str] = Field(default_factory=list)


class SemanticCanonicalProductWriteResponse(BaseModel):
    audit_id: str
    applied: bool
    command_kind: str
    affected_graph_iris: list[str]
    delta: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    validation: dict[str, Any] | None = None
    graph_revisions: dict[str, int] = Field(default_factory=dict)
    stale_derived_pointers: list[dict[str, Any]] = Field(default_factory=list)


class SemanticCanonicalModeRead(BaseModel):
    canonical_store: str
    product_write_mode: str
    read_mode: str
    legacy_write_blocked: bool
    scope_type: str | None
    scope_id: str | None
    notes: list[str] = Field(default_factory=list)


