export type JsonObject = Record<string, unknown>;

export type Notice = { kind: "ok" | "error" | "info"; message: string } | null;

export type Project = {
  id: string;
  name: string;
  description: string | null;
  created_at?: string;
  updated_at?: string;
};

export type Ontology = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  status: string;
  external_mappings?: JsonObject;
  created_at?: string;
  updated_at?: string;
};

export type ClassDef = {
  id: string;
  ontology_id: string;
  name: string;
  normalized_label?: string;
  description: string | null;
  aliases: string[];
  parent_class_ids: string[];
  external_mappings?: JsonObject;
};

export type PropertyDef = {
  id: string;
  class_id: string;
  name: string;
  type: string;
  description: string | null;
  required: boolean;
  multi_valued: boolean;
  enum_values: string[];
  constraints?: JsonObject;
  external_mappings?: JsonObject;
};

export type RelationType = {
  id: string;
  ontology_id: string;
  name: string;
  description: string | null;
  aliases: string[];
  parent_relation_type_id: string | null;
  source_class_id: string;
  target_class_id: string;
  inverse_name: string | null;
  normalized_type?: string;
  scope_policy?: "schema_allowed" | "entity_only" | "both";
  symmetric?: boolean;
  transitive?: boolean;
  status?: string;
  valid_from?: string | null;
  valid_to?: string | null;
  external_mappings?: JsonObject;
};

export type Entity = {
  id: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string | null;
  class_id: string;
  class_label: string;
  name: string;
  aliases: string[];
  properties: JsonObject;
};

export type Relation = {
  id: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string | null;
  relation_type_id: string;
  relation_type: string;
  source_entity_id: string;
  target_entity_id: string;
  properties: JsonObject;
  scope?: string;
  status?: string;
  valid_from?: string | null;
  valid_to?: string | null;
};

export type DataSource = {
  id: string;
  project_id: string;
  name: string;
  source_type: string;
  owner: string | null;
  authority_level: string;
  status: string;
  description: string | null;
  connection_policy: JsonObject;
  created_at: string;
  updated_at: string;
};

export type DataResource = {
  id: string;
  project_id: string;
  data_source_id: string;
  name: string;
  resource_type: string;
  owner: string | null;
  authority_level: string;
  status: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type ExternalField = {
  id: string;
  project_id: string;
  data_source_id: string;
  data_resource_id: string;
  name: string;
  data_type: string;
  sensitivity: "public" | "internal" | "confidential" | "restricted";
  access_policy: "allow" | "mask" | "approval_required" | "deny";
  masking_rule: string | null;
  approval_note: string | null;
  audit_required: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type SemanticMapping = {
  id: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string | null;
  target_type: "class" | "property" | "relation_type" | "entity";
  target_id: string;
  data_source_id: string;
  resource_id: string;
  field_id: string;
  external_resource_name: string;
  external_field_name: string;
  join_key: JsonObject;
  valid_from: string | null;
  valid_to: string | null;
  confidence: number;
  owner: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ConnectorTemplate = {
  id: string;
  project_id: string;
  data_source_id: string;
  name: string;
  description: string | null;
  allowed_field_ids: string[];
  parameter_schema: JsonObject;
  result_schema: JsonObject;
  access_policy: "allow" | "approval_required" | "deny";
  created_at: string;
  updated_at: string;
};

export type ConnectorQueryResult = {
  template_id: string;
  authorized: boolean;
  denial_reason: string | null;
  source: JsonObject;
  queried_at: string;
  audit: JsonObject;
  rows: JsonObject[];
};

export type IdentifierResolutionStats = {
  left_count: number;
  right_count: number;
  overlap_count: number;
  left_coverage: number;
  right_coverage: number;
  one_to_one: boolean;
  unmapped_left: string[];
  unmapped_right: string[];
};

export type EntityWithRelations = Entity & {
  outgoing: Relation[];
  incoming: Relation[];
};

export type EntityKnowledgeItem = {
  source_type: string;
  claim_id: string | null;
  predicate: string;
  value: unknown;
  anchor: JsonObject;
  layer: string | null;
  audit_status: string | null;
  confidence: number | null;
  sensitivity: string | null;
  access_policy: JsonObject;
  access_decision: string | null;
  redacted: boolean;
  evidence_ids: string[];
  generation_reason: string | null;
  relation_id: string | null;
  rule_id: string | null;
  inherited_from_class_id: string | null;
  overrides: string | null;
  overridden: boolean;
};

export type EntityKnowledgeRule = {
  id: string;
  rule_type: string;
  scope: JsonObject;
  condition: JsonObject;
  conclusion: JsonObject;
  status: string;
  priority: number;
  evidence_ids: string[];
  version: number;
};

export type EntityKnowledgeContext = {
  entity: Entity;
  class_chain: ClassDef[];
  relation_ids: string[];
  properties: EntityKnowledgeItem[];
  entity_assertions: EntityKnowledgeItem[];
  inherited_class_assertions: EntityKnowledgeItem[];
  relation_assertions: EntityKnowledgeItem[];
  rule_assertions: EntityKnowledgeItem[];
  rules: EntityKnowledgeRule[];
};

export type RelatedEntity = {
  entity: Entity;
  relations: Relation[];
};

export type EntityExplain = {
  entity: Entity;
  class_schema: (ClassDef & { properties: PropertyDef[] }) | null;
  direct_relations: Relation[];
  related_entities: RelatedEntity[];
  explain_text: string;
};

export type OntologyExport = {
  ontology: Ontology;
  classes: Array<ClassDef & { properties: PropertyDef[] }>;
  relation_types: RelationType[];
  entities: Entity[];
  relations: Relation[];
};

export type EvidenceBinding = {
  id?: string;
  fact_id?: string;
  chunk_id?: string | null;
  evidence_artifact_id?: string | null;
  document_filename?: string | null;
  sequence?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  text_preview?: string;
  text?: string;
  actor?: string | null;
  reason?: string | null;
  created_at?: string | null;
  // Legacy fields retained for read-model consumers not yet migrated to the
  // Phase 8 schema (EvidenceExplorerPanel, EvidenceBindingPanel, etc.).
  chunk_iri?: string | null;
  document_iri?: string | null;
};

/**
 * Phase 8 — fact-evidence binding record returned by
 * ``POST /api/semantic/graph-sets/{gs}/fact-evidence``. This shape mirrors
 * the backend ``FactEvidenceBinding`` Pydantic schema (backend/app/api/schemas.py)
 * and is distinct from the loose ``EvidenceBinding`` read-model projection
 * used by the composer outputs.
 */
export type FactEvidenceBinding = {
  id: string;
  fact_id: string;
  subject_iri: string;
  predicate_iri: string;
  object_value: string;
  graph_iri: string;
  chunk_id?: string | null;
  evidence_artifact_id?: string | null;
  evidence_reference_id?: string | null;
  document_filename?: string | null;
  sequence?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  text: string;
  actor?: string | null;
  reason?: string | null;
  created_at?: string | null;
};

export type MissingEvidenceFactsResponse = {
  count: number;
  fact_ids: string[];
};

export type Health = Record<string, unknown>;

export type Evidence = {
  id: string;
  proposal_id: string;
  source_type: string;
  quote: string;
  artifact_id?: string | null;
  document_id: string | null;
  page_number: number | null;
  chunk_id: string | null;
  char_start: number | null;
  char_end: number | null;
  content_hash: string;
};

export type ProposalItem = {
  key: string;
  kind: "class" | "property" | "relation_type" | "constraint" | "entity" | "relation" | "merge";
  data: JsonObject;
  confidence?: number;
  evidence_ids?: string[];
  competency_question_ids?: string[];
  review_status?: "pending" | "approved" | "rejected";
  modified?: boolean;
  merged_into_key?: string;
};

export type Proposal = {
  id: string;
  ontology_id: string;
  target_version_id: string;
  proposal_type: string;
  status: string;
  source_type: string;
  payload: { items?: ProposalItem[]; [key: string]: unknown };
  validation_result: { valid?: boolean; errors?: string[]; ambiguities?: JsonObject[] };
  application_result: JsonObject;
  evidence: Evidence[];
  created_at: string;
};

export type EvidenceArtifact = {
  id: string;
  artifact_id?: string;
  project_id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  content_hash: string;
  parse_status: string;
  parse_error: string | null;
  parser_version: string;
  parse_count: number;
  parse_revision: number;
  reused: boolean;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type EvidenceChunk = {
  id: string;
  artifact_id?: string;
  document_id: string;
  sequence: number;
  parse_revision: number;
  page_number: number | null;
  char_start: number;
  char_end: number;
  text: string;
  content_hash: string;
};

export type KnowledgeConflict = {
  id: string;
  proposal_id: string;
  item_key: string;
  field: string;
  existing_value: unknown;
  proposed_value: unknown;
  status: string;
  resolution: JsonObject;
};



export type BriefFieldState = "missing" | "answered" | "confirmed" | "skipped";

export type BriefClarificationItem = {
  field: string;
  question: string;
  reason: string;
};

export type ProjectBrief = {
  id: string | null;
  project_id: string;
  fields: JsonObject;
  field_states: Record<string, BriefFieldState>;
  field_sources: Record<string, string[]>;
  missing_fields: string[];
  clarification_items: BriefClarificationItem[];
  completeness: number;
};

export type BuildContextWorkspace = {
  state: string;
  workspace_version: string | null;
  editable: boolean;
  issues: string[];
};

export type ModelingBatchStatus =
  | "open"
  | "applying"
  | "recovering"
  | "applied"
  | "partially_applied"
  | "failed";

export type ModelingAttemptMode = "dry_run" | "apply_atomic" | "apply_partial";

export type ModelingAttemptStatus =
  | "validating"
  | "validated"
  | "validation_failed"
  | "applying"
  | "recovering"
  | "applied"
  | "partially_applied"
  | "failed";

export type ModelingFinding = {
  code: string;
  severity: "info" | "warning" | "error" | string;
  message: string;
  scope?: "batch" | "group" | "item" | string;
  client_item_id?: string | null;
  client_item_ids?: string[];
  atomic_group_id?: string | null;
  path?: string | Array<string | number> | null;
  details?: JsonObject;
  blocking?: boolean;
  retryable?: boolean;
};

export type ModelingBatchSummary = {
  id?: string;
  batch_id: string;
  client_batch_id?: string;
  build_session_id?: string;
  ontology_id: string;
  status?: ModelingBatchStatus | string;
  batch_status?: ModelingBatchStatus | string;
  latest_mode?: ModelingAttemptMode | string | null;
  latest_attempt_status?: ModelingAttemptStatus | string | null;
  item_count?: number;
  finding_count?: number;
  recovery_state?: string | null;
  latest_attempt?: {
    attempt_id: string;
    mode: ModelingAttemptMode | string;
    attempt_status: ModelingAttemptStatus | string;
    finding_count: number;
    recovery_state: string | null;
  } | null;
  created_at?: string;
  updated_at?: string;
  terminal_at?: string | null;
};

export type ModelingContext = {
  project: { id: string; name?: string; description?: string | null };
  ontology: { id: string; name: string; status: string };
  generated_at?: string;
  workspace: {
    workspace_version: string | null;
    state: string;
    editable: boolean;
    issues?: string[];
  };
  resource_counts: Record<string, number | null>;
  derived_state: {
    stale_count?: number;
    current_pointer_count?: number;
    stale_pointer_count?: number;
    current?: number;
    stale?: number;
    warning?: string | null;
    warnings?: string[];
  };
  lease: {
    active: boolean;
    fenced: boolean;
    state?: string | null;
  };
  recovering?: {
    active: boolean;
    attempt_id: string | null;
  };
  recent_batches: ModelingBatchSummary[];
  recent_batches_next_cursor?: string | null;
  batch_history: string;
  query_entries: JsonObject | JsonObject[];
};

export type ModelingBatchItemResult = {
  item_id?: string;
  modeling_item_id?: string;
  client_item_id: string;
  command_kind?: string;
  status?: string;
  atomic_group_id?: string | null;
  resource_outputs?: JsonObject;
  finding_codes?: string[];
};

export type ModelingBatchImmutableItem = ModelingBatchItemResult & {
  ordinal?: number;
  payload?: JsonObject;
  depends_on?: string[];
  evidence_reference_ids?: string[];
  rationale?: string | null;
  competency_question_ids?: string[];
};

export type ModelingBatchAttempt = {
  id?: string;
  attempt_id?: string;
  mode: ModelingAttemptMode | string;
  status?: ModelingAttemptStatus | string;
  attempt_status?: ModelingAttemptStatus | string;
  findings?: ModelingFinding[];
  items?: ModelingBatchItemResult[];
  recovery?: JsonObject;
  recovery_state?: string | null;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
};

export type ModelingBatchDetail = {
  id?: string;
  batch_id: string;
  client_batch_id: string;
  build_session_id?: string;
  ontology_id?: string;
  status?: ModelingBatchStatus | string;
  batch_status: ModelingBatchStatus | string;
  attempt_id?: string;
  mode?: ModelingAttemptMode | string;
  attempt_status?: ModelingAttemptStatus | string;
  workspace?: JsonObject;
  items: ModelingBatchImmutableItem[];
  groups?: JsonObject[];
  findings?: ModelingFinding[];
  attempts: ModelingBatchAttempt[];
  recovery?: JsonObject;
  recovery_history?: JsonObject[];
  created_at?: string;
  completed_at?: string | null;
};

export type ModelingBatchPage = {
  items?: ModelingBatchSummary[];
  batches?: ModelingBatchSummary[];
  next_cursor: string | null;
};

export type BuildContextOntology = {
  id: string;
  name: string;
  status: string;
  workspace: BuildContextWorkspace;
};

export type BuildFailure = {
  code: string;
  message: string;
};

export type BuildCheckpoint = {
  id: string;
  build_session_id: string;
  client_checkpoint_id: string;
  sequence: number;
  ontology_id: string | null;
  phase: string;
  current_step: string;
  next_step: string | null;
  summary: string | null;
  blockers: string[];
  failure: BuildFailure | null;
  related_batch_id: string | null;
  reported_by: string | null;
  created_at: string;
};

export type BuildSessionStatus = "active" | "completed" | "cancelled";

export type BuildSessionSummary = {
  id: string;
  project_id: string;
  client_session_id: string;
  previous_session_id: string | null;
  status: BuildSessionStatus;
  revision: number;
  created_by: string | null;
  completion_summary: string | null;
  unresolved_items: string[];
  cancel_reason: string | null;
  last_activity_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  latest_checkpoint: BuildCheckpoint | null;
};

export type OntologyLeaseSummary = {
  ontology_id: string;
  build_session_id: string;
  lease_revision: number;
  state: "active" | "expired" | "released";
  acquired_at: string;
  renewed_at: string | null;
  expires_at: string;
  released_at: string | null;
};

export type BuildSessionDetail = {
  session: BuildSessionSummary;
  latest_checkpoint: BuildCheckpoint | null;
  checkpoints: BuildCheckpoint[];
  checkpoints_next_cursor: number | null;
  involved_ontology_ids: string[];
  leases: OntologyLeaseSummary[];
  modeling_batches: JsonObject[];
  evidence: JsonObject;
  recent_activity: JsonObject[];
};

export type BuildContext = {
  project: Pick<Project, "id" | "name" | "description">;
  generated_at: string;
  platform_state: {
    project_brief: ProjectBrief;
    competency_question_counts: Record<string, number>;
    ontologies: BuildContextOntology[];
    evidence_reference_count: number;
    modeling_batches: JsonObject[];
  };
  agent_state: {
    active_sessions: BuildSessionSummary[];
    recent_sessions: BuildSessionSummary[];
    recent_sessions_next_cursor: number | null;
    unresolved_items: string[];
  };
};

export type CompetencyQuestionStatus = "draft" | "approved" | "testable" | "passed" | "failed";

export type CompetencyQuestion = {
  id: string;
  project_id: string;
  ontology_id: string;
  question: string;
  importance: number;
  position: number;
  status: CompetencyQuestionStatus;
  active: boolean;
  query_definition: JsonObject;
  validation_result: JsonObject;
  source_answer_ids: string[];
  source_brief_fields: string[];
  created_at: string;
  updated_at: string;
};

export type FactClaimType = "direct" | "inferred" | "conflict" | "low_confidence";
export type FactClaimLayer =
  | "entity_attribute"
  | "entity_relation"
  | "inferred_inverse"
  | "low_confidence"
  | "value_conflict"
  | "cq_answer";
export type FactAuditStatus = "pending" | "approved" | "rejected" | "needs_correction";

export type FactClaim = {
  id: string;
  claim_key: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string;
  claim_type: FactClaimType;
  layer: FactClaimLayer;
  subject: JsonObject;
  predicate: string;
  value: unknown;
  graph_path: JsonObject[];
  evidence_ids: string[];
  generation_reason: string;
  confidence: number;
  audit_status: FactAuditStatus;
  review_decision: JsonObject;
  linked_fix_proposal_id: string | null;
  stale: boolean;
  stale_reason: string | null;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
};

export type PublicationGateType =
  | "schema_validation"
  | "pending_proposals"
  | "unresolved_conflicts"
  | "low_confidence_review"
  | "evidence_coverage"
  | "competency_questions"
  | "fact_audit";
export type PublicationGateStatus = "pending" | "passed" | "failed" | "warning";

export type PublicationGate = {
  gate_type: PublicationGateType;
  status: PublicationGateStatus;
  details: JsonObject;
  checked_at: string;
};

export type PublicationReadiness = {
  version_id: string;
  ready: boolean;
  gates: PublicationGate[];
  blocking: PublicationGateType[];
  warnings: PublicationGateType[];
};

// ---------------------------------------------------------------------------
// Phase 8 — semantic graph governance DTOs mirroring /api/semantic/*
// ---------------------------------------------------------------------------

export type SemanticJsonObject = Record<string, unknown>;

export type SemanticGraphCategory =
  | "ontology"
  | "data"
  | "proposal"
  | "evidence"
  | "policy"
  | "import"
  | "validation_run"
  | "reasoning_run"
  | "reasoning_result"
  | "rule_run"
  | "rule_result"
  | "review"
  | "shape"
  | "namespace"
  | "other";

export type SemanticGraphRegistryRead = {
  graph_iri: string;
  category: string;
  registered: boolean;
  owner_type: string | null;
  owner_id: string | null;
  mutable_by_direct_edit: boolean | null;
  editable: boolean | null;
  editability_reason: string | null;
  revision: number | null;
  content_hash: string | null;
  derived_pointers: SemanticJsonObject[];
  metadata: SemanticJsonObject;
  statement_count: number | null;
  latest_audit_at: string | null;
};

export type SemanticGraphRegistryListResponse = {
  graphs: SemanticGraphRegistryRead[];
  summary: SemanticJsonObject;
};

export type SemanticGraphMember = {
  graph_iri: string;
  role: string;
  required: boolean;
  sort_order: number;
  metadata: SemanticJsonObject;
};

export type SemanticGraphSetRead = {
  id: string;
  name: string;
  scope_type: string;
  scope_id: string | null;
  status: string;
  source_signature: string;
  created_by: string | null;
  members: SemanticGraphMember[];
  current_pointers: SemanticJsonObject[];
  metadata: SemanticJsonObject;
};

export type SemanticGraphSetListResponse = {
  graph_sets: SemanticGraphSetRead[];
};

export type SemanticGovernanceStatusResponse = {
  graphs: SemanticJsonObject;
  derived: SemanticJsonObject;
};

export type SemanticEditAuditRead = {
  id: string;
  actor: string | null;
  reason: string | null;
  input_format: string;
  target_graph_iri: string | null;
  affected_graph_iris: string[];
  validation_result: SemanticJsonObject | null;
  graph_delta: SemanticJsonObject;
  evidence_status: string | null;
  warning_state: SemanticJsonObject;
  applied: boolean;
  created_at: string;
};

export type SemanticEditResponse = {
  audit_id: string | null;
  applied: boolean;
  affected_graph_iris: string[];
  delta: SemanticJsonObject;
  warnings: string[];
  validation: SemanticJsonObject | null;
  graph_revisions: Record<string, number>;
  stale_derived_pointers: SemanticJsonObject[];
  parse_error: SemanticEditParseError | null;
  error: string | null;
};

export type SemanticEditParseError = {
  message: string;
  line: number | null;
  column: number | null;
};

export type SemanticGraphEditabilityResponse = {
  graph_iri: string;
  editable: boolean;
  updated_by: string | null;
  reason: string | null;
};

export type SemanticValidationRunRead = {
  run_id: string;
  status: string;
  conforms: boolean | null;
  report_graph_iri: string | null;
  summary: SemanticJsonObject;
  guidance: SemanticJsonObject;
  warnings: string[];
  graph_set_id: string | null;
  source_signature: string;
  input_graph_revisions: Record<string, number>;
  shape_version: string | null;
  engine_version: string | null;
  validation_scope: string;
  missing_evidence_dependencies: SemanticJsonObject;
  staleness: SemanticJsonObject;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
};

export type SemanticReasoningRunRead = {
  run_id: string;
  status: string;
  consistent: boolean | null;
  classification: SemanticJsonObject;
  entailments: SemanticJsonObject[];
  result_graph_iri: string | null;
  graph_set_id: string | null;
  source_signature: string;
  input_graph_revisions: Record<string, number>;
  input_derived_pointers: SemanticJsonObject;
  engine_version: string | null;
  shape_version: string | null;
  tasks: string[];
  profile: string;
  missing_evidence_dependencies: SemanticJsonObject;
  warnings: string[];
  derived_pointer: SemanticJsonObject | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
};

export type SemanticRuleRunRead = {
  run_id: string;
  status: string;
  engine_name: string;
  engine_version: string | null;
  graph_set_id: string;
  rule_definition_id: string | null;
  rule_version: string | null;
  result_graph_iri: string | null;
  rule_run_graph_iri: string | null;
  generated_statement_count: number;
  statements: SemanticJsonObject[];
  bindings: SemanticJsonObject[];
  warnings: string[];
  truncated: boolean;
  missing_evidence_dependencies: SemanticJsonObject;
  audit_status: string;
  explanations: SemanticJsonObject[];
  rule_count: number | null;
  derived_pointer: SemanticJsonObject | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
};

export type SemanticRunListSummary = {
  total: number;
  stale_count: number;
  superseded_count: number;
};

export type SemanticValidationRunListResponse = {
  items: SemanticValidationRunRead[];
  summary: SemanticRunListSummary;
};

export type SemanticReasoningRunListResponse = {
  items: SemanticReasoningRunRead[];
  summary: SemanticRunListSummary;
};

export type SemanticRuleRunListResponse = {
  items: SemanticRuleRunRead[];
  summary: SemanticRunListSummary;
};

export type SemanticRuleDefinitionRead = {
  id: string;
  rule_iri: string;
  name: string;
  language: string;
  version: string;
  status: string;
  body: SemanticJsonObject;
  input_roles: string[];
  output_kind: string;
  uses_inferred_facts: boolean;
  requires_review: boolean;
  priority: number;
  safety_profile: SemanticJsonObject;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  metadata: SemanticJsonObject;
};

export type SemanticRuleDefinitionListResponse = {
  rules: SemanticRuleDefinitionRead[];
};

export type SemanticStatementItem = {
  id: string;
  iri: string;
  label: string | null;
  source_graph_iri: string;
  assertion_kind: string;
  evidence_ids: string[];
  provenance: SemanticJsonObject;
  audit_status: string | null;
  staleness: SemanticJsonObject;
};

export type SemanticReadModelEnvelope = {
  graph_set_id: string;
  source_signature: string;
  projection_version: string;
  include: string;
  derived_state: SemanticJsonObject;
  warnings: SemanticJsonObject[];
  items: SemanticStatementItem[];
};

export type SemanticDerivedResultReconcileResponse = {
  graph_sets_inspected: number;
  pointers_marked_current: number;
  pointers_marked_stale: number;
};

export type SemanticGraphGcResponse = {
  gc_run_id: string;
  target_kind: string;
  status: string;
  candidate_count: number;
  deleted_count: number;
  dry_run: boolean;
  deleted_graph_iris: string[];
  errors: SemanticJsonObject[];
};

export type SemanticProjectionJobRead = {
  id: string;
  graph_set_id: string | null;
  projection_kind: string;
  projection_version: string;
  projection_scope: string;
  source_signature: string;
  input_graph_revisions: SemanticJsonObject;
  input_derived_pointers: SemanticJsonObject;
  target_store: string | null;
  target_partition: string | null;
  status: string;
  node_count: number;
  relationship_count: number;
  document_count: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  metadata: SemanticJsonObject;
};

export type SemanticProjectionJobListResponse = {
  items: SemanticProjectionJobRead[];
  total: number;
};

export type SemanticProjectionStatusResponse = {
  manifests: SemanticJsonObject[];
  stale: string[];
  missing: string[];
  stale_projection_count: number;
};

export type SemanticSparqlQueryResponse = {
  result: unknown;
  result_format: string;
  query_type: "select" | "ask" | "construct" | "describe";
  scope: {
    project_id: string;
    mode: "project" | "ontologies";
    status: "complete" | "partial";
    ontologies: Array<Record<string, unknown>>;
    excluded_ontologies: Array<Record<string, unknown>>;
  };
  truncated: boolean;
  warnings: Array<{ code: string; message: string }>;
};

export type SemanticDatasetLoadResponse = {
  loaded: boolean;
  format: string;
  graph_count: number | null;
  triple_count: number | null;
  warnings: string[];
};

export type SemanticCanonicalModeRead = {
  canonical_store: string;
  product_write_mode: string;
  read_mode: string;
  legacy_write_blocked: boolean;
  scope_type: string | null;
  scope_id: string | null;
  notes: string[];
};

export type SemanticEditInputFormat = "trig" | "turtle" | "json-ld" | "sparql-update";
export type SemanticExportFormat = "trig" | "turtle" | "json-ld";
export type SemanticExportInclude =
  | "asserted"
  | "asserted-plus-reasoning"
  | "asserted-plus-rules"
  | "full-working-view";
