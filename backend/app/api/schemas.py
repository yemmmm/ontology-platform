from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.ontology import PropertyType  # noqa: F401 - kept for downstream imports


# ---------------------------------------------------------------------------
# Project + ontology CRUD (frontend OntologyHomePage contract)
# ---------------------------------------------------------------------------


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
    name: str
    description: str | None
    status: str
    external_mappings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyWorkspaceMemberRead(BaseModel):
    role: str
    graph_iri: str
    category: str
    required: bool
    revision: int | None
    content_hash: str | None
    editable: bool
    editability_reason: str | None = None
    owner_type: str | None = None
    owner_id: str | None = None


class OntologyWorkspaceContextRead(BaseModel):
    ontology_id: str
    state: Literal["ready", "incomplete"]
    default_graph_set_id: str | None
    graph_set_status: str | None
    source_signature: str | None
    members: list[OntologyWorkspaceMemberRead]
    issues: list[str]


class OntologyCreateResponse(OntologyRead):
    workspace: OntologyWorkspaceContextRead


class OntologyWorkspaceRepairRequest(BaseModel):
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Interview / brief / competency questions (Stage 1 disposition K)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# R-003 external Agent build sessions
# ---------------------------------------------------------------------------


class BuildSessionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuildFailure(BuildSessionSchema):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=10000)


class BuildCheckpointInput(BuildSessionSchema):
    phase: Literal["intake", "modeling", "verification", "handoff"]
    current_step: str = Field(min_length=1, max_length=4000)
    next_step: str | None = Field(default=None, max_length=4000)
    ontology_id: str | None = Field(default=None, min_length=1, max_length=36)
    summary: str | None = Field(default=None, max_length=20000)
    blockers: list[str] = Field(default_factory=list, max_length=100)
    failure: BuildFailure | None = None
    related_batch_id: str | None = Field(default=None, min_length=1, max_length=36)


class InitialBuildCheckpoint(BuildCheckpointInput):
    client_checkpoint_id: str = Field(min_length=1, max_length=255)


class BuildSessionCreate(BuildSessionSchema):
    client_session_id: str = Field(min_length=1, max_length=255)
    previous_session_id: str | None = Field(default=None, min_length=1, max_length=36)
    initial_checkpoint: InitialBuildCheckpoint | None = None


class BuildSessionResume(BuildSessionSchema):
    client_request_id: str = Field(min_length=1, max_length=255)
    expected_revision: int = Field(ge=1)


class BuildCheckpointCreate(BuildCheckpointInput):
    client_checkpoint_id: str = Field(min_length=1, max_length=255)
    expected_revision: int = Field(ge=1)


class BuildSessionComplete(BuildSessionSchema):
    client_request_id: str = Field(min_length=1, max_length=255)
    expected_revision: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=20000)
    unresolved_items: list[str] = Field(default_factory=list, max_length=100)


class BuildSessionCancel(BuildSessionSchema):
    client_request_id: str = Field(min_length=1, max_length=255)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=10000)


class OntologyLeaseAcquire(BuildSessionSchema):
    client_request_id: str = Field(min_length=1, max_length=255)
    expected_session_revision: int = Field(ge=1)
    rotate_token: bool = False


class OntologyLeaseRenew(BuildSessionSchema):
    client_request_id: str = Field(min_length=1, max_length=255)
    lease_token: str = Field(min_length=1, max_length=1024)
    expected_lease_revision: int = Field(ge=1)


class OntologyLeaseRelease(OntologyLeaseRenew):
    pass


class BuildCheckpointRead(BaseModel):
    id: str
    build_session_id: str
    client_checkpoint_id: str
    sequence: int
    ontology_id: str | None
    phase: str
    current_step: str
    next_step: str | None
    summary: str | None
    blockers: list[str]
    failure: BuildFailure | None
    related_batch_id: str | None
    reported_by: str | None
    created_at: datetime


class OntologyLeaseSummaryRead(BaseModel):
    ontology_id: str
    build_session_id: str
    lease_revision: int
    state: Literal["active", "expired", "released"]
    acquired_at: datetime
    renewed_at: datetime | None
    expires_at: datetime
    released_at: datetime | None


class OntologyLeaseTokenRead(BaseModel):
    ontology_id: str
    build_session_id: str
    lease_token: str | None = None
    lease_revision: int
    expires_at: datetime
    state: Literal["active", "expired", "released"] = "active"


class BuildSessionSummaryRead(BaseModel):
    id: str
    project_id: str
    client_session_id: str
    previous_session_id: str | None
    status: Literal["active", "completed", "cancelled"]
    revision: int
    created_by: str | None
    completion_summary: str | None
    unresolved_items: list[str]
    cancel_reason: str | None
    last_activity_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    latest_checkpoint: BuildCheckpointRead | None = None


class BuildSessionDetailRead(BaseModel):
    session: BuildSessionSummaryRead
    latest_checkpoint: BuildCheckpointRead | None
    checkpoints: list[BuildCheckpointRead]
    checkpoints_next_cursor: int | None
    involved_ontology_ids: list[str]
    leases: list[OntologyLeaseSummaryRead]
    modeling_batches: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    recent_activity: list[dict[str, Any]] = Field(default_factory=list)
    modeling_workflow_summary: dict[str, Any] = Field(default_factory=dict)


class ProjectBuildContextRead(BaseModel):
    project: dict[str, Any]
    generated_at: datetime
    platform_state: dict[str, Any]
    agent_state: dict[str, Any]


# ---------------------------------------------------------------------------
# R1.1-002 versioned modeling workflow records
# ---------------------------------------------------------------------------


WorkflowArtifactType = Literal[
    "business_knowledge_pack",
    "modeling_coverage_matrix",
    "modeling_draft",
    "review_report",
    "verification_report",
]
WorkflowRole = Literal[
    "business_organizer",
    "modeler",
    "reviewer",
    "main_agent",
    "user",
    "platform",
]
WorkflowPhase = Literal[
    "recovery",
    "global_scan",
    "business_confirmation",
    "core_modeling",
    "dry_run",
    "review",
    "apply",
    "verification",
    "expansion_or_handoff",
]
WorkflowEventType = Literal[
    "source_scanned",
    "artifact_created",
    "question_asked",
    "answer_recorded",
    "decision_recorded",
    "dry_run_completed",
    "review_completed",
    "rework_requested",
    "batch_applied",
    "verification_completed",
    "phase_completed",
    "blocked",
]


class ModelingWorkflowSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelingWorkflowArtifactCreate(ModelingWorkflowSchema):
    client_version_id: str = Field(min_length=1, max_length=255)
    artifact_key: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    artifact_type: WorkflowArtifactType
    content_format: Literal["json", "markdown"]
    content: Any
    created_by_role: WorkflowRole
    workflow_name: str = Field(min_length=1, max_length=120)
    workflow_version: str = Field(min_length=1, max_length=120)
    role_prompt_version: str | None = Field(default=None, max_length=120)
    ontology_id: str | None = Field(default=None, min_length=1, max_length=36)
    supersedes_workflow_artifact_id: str | None = Field(default=None, min_length=1, max_length=36)


class WorkflowRelatedResource(ModelingWorkflowSchema):
    resource_type: Literal[
        "competency_question",
        "evidence_reference",
        "modeling_batch",
        "modeling_attempt",
        "finding",
        "validation_run",
        "lineage",
        "ontology",
        "lease",
        "workflow_artifact",
        "execution_event",
    ]
    resource_id: str | None = Field(default=None, min_length=1, max_length=512)
    attempt_id: str | None = Field(default=None, min_length=1, max_length=36)
    finding_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    ontology_id: str | None = Field(default=None, min_length=1, max_length=36)
    target_type: Literal["statement", "resource", "rule"] | None = None
    target_id: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.resource_type == "finding":
            if not self.attempt_id or not self.finding_fingerprint or self.resource_id:
                raise ValueError("finding requires attempt_id and finding_fingerprint only")
        elif self.resource_type == "lineage":
            if not self.ontology_id or not self.target_type or not self.target_id:
                raise ValueError("lineage requires ontology_id, target_type, and target_id")
        elif not self.resource_id:
            raise ValueError(f"{self.resource_type} requires resource_id")
        return self


class ModelingQualityIssue(ModelingWorkflowSchema):
    issue_category: Literal[
        "knowledge_omission",
        "term_conflict",
        "identity_error",
        "relation_error",
        "granularity_error",
        "insufficient_evidence",
        "competency_question_gap",
        "over_modeling",
        "stale_knowledge",
        "other",
    ]
    introduced_phase: WorkflowPhase | Literal["unknown"]
    detected_phase: WorkflowPhase
    detected_by_role: WorkflowRole
    severity: Literal["critical", "high", "medium", "low"]
    rework_count: int | None = Field(default=None, ge=0)
    rework_duration_ms: int | None = Field(default=None, ge=0)
    preventable_at: WorkflowPhase | Literal["unknown"]
    root_cause: Literal["unknown", "hypothesis"] = "unknown"
    root_cause_hypothesis: str | None = Field(default=None, max_length=4000)
    description: str = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def validate_root_cause(self):
        if self.root_cause == "hypothesis" and not self.root_cause_hypothesis:
            raise ValueError("root_cause_hypothesis is required for hypothesis")
        if self.root_cause == "unknown" and self.root_cause_hypothesis:
            raise ValueError("unknown root cause cannot include a hypothesis")
        return self


class ModelingExecutionEventCreate(ModelingWorkflowSchema):
    client_event_id: str = Field(min_length=1, max_length=255)
    ontology_id: str | None = Field(default=None, min_length=1, max_length=36)
    workflow_name: str = Field(min_length=1, max_length=120)
    workflow_version: str = Field(min_length=1, max_length=120)
    phase: WorkflowPhase
    event_type: WorkflowEventType
    status: Literal["started", "recorded", "completed", "failed", "blocked"]
    report_source: Literal["agent_reported", "user_reported"]
    actor_role: WorkflowRole
    role_prompt_version: str | None = Field(default=None, max_length=120)
    agent_runtime: str | None = Field(default=None, max_length=120)
    agent_model: str | None = Field(default=None, max_length=120)
    reasoning_effort: str | None = Field(default=None, max_length=40)
    summary: str = Field(min_length=1, max_length=10000)
    input_workflow_artifact_ids: list[str] = Field(default_factory=list, max_length=100)
    output_workflow_artifact_ids: list[str] = Field(default_factory=list, max_length=100)
    question_id: str | None = Field(default=None, min_length=1, max_length=255)
    question_state: Literal["open", "answered", "skipped", "uncertain", "reopened"] | None = None
    question_text: str | None = Field(default=None, max_length=10000)
    answer_text: str | None = Field(default=None, max_length=20000)
    answer_reason: str | None = Field(default=None, max_length=10000)
    expected_question_head_event_id: str | None = Field(default=None, min_length=1, max_length=36)
    interview_answer_id: str | None = Field(default=None, min_length=1, max_length=36)
    decisions: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    rejected_alternatives: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    unresolved_items: list[str] = Field(default_factory=list, max_length=100)
    blockers: list[str] = Field(default_factory=list, max_length=100)
    next_step: str | None = Field(default=None, max_length=10000)
    related_resources: list[WorkflowRelatedResource] = Field(default_factory=list, max_length=200)
    quality_issues: list[ModelingQualityIssue] = Field(default_factory=list, max_length=100)
    duration_ms: int | None = Field(default=None, ge=0)
    token_usage: dict[str, int | None] = Field(default_factory=dict)
    cost_summary: dict[str, float | str | None] = Field(default_factory=dict)
    supersedes_execution_event_id: str | None = Field(default=None, min_length=1, max_length=36)
    occurred_at: datetime | None = None


# ---------------------------------------------------------------------------
# R-004 immutable Modeling Batch protocol
# ---------------------------------------------------------------------------


class ModelingBatchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InlineModelingEvidence(ModelingBatchSchema):
    document_name: str = Field(min_length=1, max_length=255)
    excerpt: str = Field(min_length=1)


class ModelingItemInput(ModelingBatchSchema):
    client_item_id: str = Field(min_length=1, max_length=255)
    command_kind: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any]
    depends_on: list[str] = Field(default_factory=list)
    evidence_reference_ids: list[str] = Field(default_factory=list)
    evidence: list[InlineModelingEvidence] = Field(default_factory=list)
    rationale: str | None = Field(default=None, max_length=20_000)
    competency_question_ids: list[str] = Field(default_factory=list)


class ModelingBatchSubmit(ModelingBatchSchema):
    client_batch_id: str = Field(min_length=1, max_length=255)
    ontology_id: str = Field(min_length=1, max_length=36)
    idempotency_key: str = Field(min_length=1, max_length=255)
    mode: Literal["dry_run", "apply_atomic", "apply_partial"] = "apply_atomic"
    expected_workspace_version: str = Field(min_length=1, max_length=128)
    lease_token: str | None = Field(default=None, min_length=1, max_length=1024)
    # Compatibility hint only.  The authenticated REST/MCP principal is the
    # sole audit actor; this client-supplied value is intentionally ignored.
    actor: str | None = Field(default=None, max_length=255)
    items: list[ModelingItemInput] = Field(min_length=1)


class ModelingOperationPlanEvidenceRead(ModelingBatchSchema):
    """Safe, source-minimal Evidence projection for a dry-run Attempt.

    The persisted Attempt plan contains internal reference and association IDs
    (and, for inline Evidence, the submitted excerpt).  The public dry-run
    receipt exposes only the fields needed to compare a candidate-local map;
    locators, owner identities, and raw source text never cross this boundary.
    """

    client_item_id: str = Field(min_length=1, max_length=255)
    document_name: str = Field(min_length=1, max_length=255)
    normalized_excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dedupe_identity: str = Field(min_length=1, max_length=255)


class ModelingOperationPlanRead(ModelingBatchSchema):
    """Additive safe operation-plan fields returned for dry-run Attempts."""

    evidence: list[ModelingOperationPlanEvidenceRead] = Field(default_factory=list)


class ValidationFindingRead(BaseModel):
    finding_fingerprint: str | None = None
    code: str
    severity: Literal["error", "warning", "info"]
    scope: Literal["batch", "group", "item"]
    client_item_ids: list[str] = Field(default_factory=list)
    path: list[str | int] = Field(default_factory=list)
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    blocking: bool
    retryable: bool = False


# ---------------------------------------------------------------------------
# Semantic stack: legacy direct-call endpoints still mounted under /semantic/*
# ---------------------------------------------------------------------------


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


class SemanticQueryScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=36)
    scope_mode: Literal["project", "ontologies"]
    ontology_ids: list[str] = Field(default_factory=list, max_length=50)


class SemanticDiscoveryQueryScope(BaseModel):
    project_id: str
    scope_mode: Literal["project", "ontologies"]
    ontology_ids: list[str] = Field(default_factory=list)


class SemanticDiscoveryExcludedOntology(BaseModel):
    ontology_id: str
    ontology_name: str
    reason: str


class SemanticDiscoveryProjectSummary(BaseModel):
    id: str
    name: str
    description: str | None


class SemanticDiscoveryProjectItem(BaseModel):
    resource_type: Literal["project"]
    id: str
    name: str
    description: str | None
    matched_on: list[Literal["id", "name", "project"]] = Field(default_factory=list)
    query_status: Literal["complete", "partial", "unavailable"]
    query_scope: SemanticDiscoveryQueryScope
    excluded_ontologies: list[SemanticDiscoveryExcludedOntology] = Field(default_factory=list)


class SemanticDiscoveryOntologyItem(BaseModel):
    resource_type: Literal["ontology"]
    id: str
    project: SemanticDiscoveryProjectSummary
    name: str
    description: str | None
    status: Literal["draft", "active", "archived"]
    queryable: bool
    unavailable_reason: Literal["ontology_archived", "workspace_not_ready"] | None
    workspace_version: str | None
    derived_warnings: list[dict[str, str]] = Field(default_factory=list)
    matched_on: list[Literal["id", "name", "project"]] = Field(default_factory=list)
    query_scope: SemanticDiscoveryQueryScope


class SemanticScopeDiscoveryResponse(BaseModel):
    items: list[SemanticDiscoveryProjectItem | SemanticDiscoveryOntologyItem]
    has_more: bool
    next_cursor: str | None
    generated_at: datetime


class SemanticContextQueryRequest(SemanticQueryScopeRequest):
    queries: list[str] | None = Field(default=None, min_length=1, max_length=8)
    query: str | None = Field(default=None, min_length=1, max_length=2000)
    resource_types: (
        list[Literal["concept", "instance", "relation", "fact", "rule", "operation"]] | None
    ) = None
    assertion_types: list[Literal["asserted", "derived"]] | None = None
    search_mode: Literal["hybrid", "lexical"] = "hybrid"
    depth: int = Field(default=1, ge=0, le=3)
    limit: int = Field(default=20, ge=1, le=100)
    context_limit: int = Field(default=100, ge=0, le=1000)
    match_cursor: str | None = Field(default=None, min_length=1, max_length=4096)
    context_cursor: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def _validate_query_and_cursors(self) -> "SemanticContextQueryRequest":
        if (self.queries is None) == (self.query is None):
            raise ValueError(
                "Provide exactly one of 'queries' or 'query'"
            )
        if self.queries is not None:
            trimmed = [item.strip() for item in self.queries]
            if any(not item for item in trimmed):
                raise ValueError("'queries' must contain non-empty expressions")
            if any(len(item) > 2000 for item in trimmed):
                raise ValueError("'queries' entries must contain at most 2000 characters")
            if sum(len(item) for item in trimmed) > 8000:
                raise ValueError("'queries' aggregate length must not exceed 8000 characters")
            object.__setattr__(self, "queries", trimmed)
        if (self.match_cursor is not None) and (self.context_cursor is not None):
            raise ValueError(
                "Provide at most one of 'match_cursor' or 'context_cursor'"
            )
        return self


class SemanticContextQueryResponse(BaseModel):
    query: dict[str, Any]
    result_status: Literal["matched", "no_match"]
    scope: dict[str, Any]
    primary_matches: list[dict[str, Any]] = Field(default_factory=list)
    related_context: list[dict[str, Any]] = Field(default_factory=list)
    matches_page: dict[str, Any] = Field(default_factory=dict)
    context_page: dict[str, Any] = Field(default_factory=dict)
    truncated: bool = False
    recall: dict[str, Any] = Field(default_factory=dict)
    warnings: list[dict[str, str]] = Field(default_factory=list)


class SemanticSparqlQueryRequest(SemanticQueryScopeRequest):
    query: str = Field(min_length=1, max_length=100000)
    timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    result_limit: int | None = Field(default=None, gt=0, le=10000)


class SemanticSparqlQueryResponse(BaseModel):
    result: Any
    result_format: str
    query_type: Literal["select", "ask", "construct", "describe"]
    scope: dict[str, Any]
    truncated: bool = False
    warnings: list[dict[str, str]] = Field(default_factory=list)


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
    warning_state: dict[str, Any] = Field(default_factory=dict)


class SemanticEditParseError(BaseModel):
    """Structured RDF parse error surfaced to the edit workbench.

    ``line`` and ``column`` are extracted from rdflib exception text when the
    parser emits the standard ``at line N, column M`` or ``at offset N`` form.
    Both fields are ``None`` when extraction fails, in which case the flat
    ``message`` remains the source of truth.
    """

    message: str
    line: int | None = None
    column: int | None = None


class SemanticEditResponse(BaseModel):
    audit_id: str | None = None
    applied: bool
    affected_graph_iris: list[str]
    delta: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    validation: dict[str, Any] | None = None
    graph_revisions: dict[str, int] = Field(default_factory=dict)
    stale_derived_pointers: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_indexes: list[dict[str, Any]] = Field(default_factory=list)
    # Stage 5 §4.5 — structured parse error. Only populated when parsing the
    # edit content failed; absent on successful preview/apply. Backwards-
    # compatible: existing consumers can ignore this field.
    parse_error: SemanticEditParseError | None = None
    # Stage 5 §4.5 — convenience flat error string preserved for backwards
    # compatibility with consumers that do not understand ``parse_error``.
    error: str | None = None


class SemanticEditPreviewResponse(SemanticEditResponse):
    """Dedicated preview envelope.

    Stage 5 §4.5 documents this as the would-be preview response shape. The
    edit workbench today reuses ``POST /edits`` with ``validate=false`` as its
    preview path, so this schema is provided as the canonical contract for
    future callers and for the typed frontend client.
    """

    pass


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


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Semantic stack: graph registry, graph sets, governance, validation, rules
# ---------------------------------------------------------------------------


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
    # Stage 5 §4.3 — request-time derived fields. Both are nullable: the
    # statement count is ``None`` when the graph is not materialised in the
    # Oxigraph store (e.g. policy-only graphs); the audit timestamp is
    # ``None`` when no edit audit has touched the graph yet.
    statement_count: int | None = None
    latest_audit_at: datetime | None = None


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
    is_default: bool = False
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
    ontology_id: str = Field(min_length=1, max_length=36)
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
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticRuleDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    priority: int | None = None
    metadata: dict[str, Any] | None = None


class SemanticRuleDefinitionRead(BaseModel):
    id: str
    ontology_id: str | None = None
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
    audit_status: str = "system_accepted"
    explanations: list[dict[str, Any]] = Field(default_factory=list)
    rule_count: int | None = None
    derived_pointer: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


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
    warnings: list[str] = Field(default_factory=list)
    derived_pointer: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class RunListSummary(BaseModel):
    """Stage 5 §4.1 — common summary block for ``*-runs`` list endpoints."""

    total: int = 0
    stale_count: int = 0
    superseded_count: int = 0


class ValidationRunListResponse(BaseModel):
    items: list[SemanticValidationRunRead]
    summary: RunListSummary


class ReasoningRunListResponse(BaseModel):
    items: list[SemanticReasoningRunRead]
    summary: RunListSummary


class RuleRunListResponse(BaseModel):
    items: list[SemanticRuleRunRead]
    summary: RunListSummary


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
    recall: dict[str, Any] | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)


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
    projection_kind: Literal["business_json", "search", "vector", "export_cache"]
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
    retrieval_index: dict[str, Any] | None = None


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


class SemanticProjectionStatusResponse(BaseModel):
    manifests: list[dict[str, Any]]
    stale: list[str]
    missing: list[str]
    # Stage 5 §4.2 — scalar form of ``len(stale)`` so the governance tile can
    # render the count without re-walking the list client-side. Always equals
    # ``len(stale)``; non-breaking.
    stale_projection_count: int = 0


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
            "update_fact",
            "delete_fact",
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
    client_item_id: str | None = None
    evidence_target_id: str | None = None
    evidence_reference_ids: list[str] = Field(default_factory=list)
    evidence: list[dict[str, str]] = Field(default_factory=list)


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
    retrieval_indexes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_associations: list[dict[str, Any]] = Field(default_factory=list)


class SemanticCanonicalModeRead(BaseModel):
    canonical_store: str
    product_write_mode: str
    read_mode: str
    legacy_write_blocked: bool
    scope_type: str | None
    scope_id: str | None
    notes: list[str] = Field(default_factory=list)
