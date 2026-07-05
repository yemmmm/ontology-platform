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
  current_version_id: string | null;
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

export type EntitySearchResult = {
  results: Array<Entity & {
    score: number;
    match_source: "text" | "vector" | "hybrid";
  }>;
  count: number;
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

export type AgentTestResponse = {
  answer: string;
  tool_calls: JsonObject[];
  graph_context: JsonObject;
  prompt_preview: string;
  warnings: string[];
  errors: string[];
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

export type WorkflowStatus =
  | "gathering"
  | "schema_draft"
  | "schema_review"
  | "graph_building"
  | "graph_review"
  | "validated"
  | "published";

export type VersionStatus = "draft" | "published";

export type OntologyVersion = {
  id: string;
  ontology_id: string;
  parent_version_id: string | null;
  version_number: number;
  status: VersionStatus;
  workflow_status: WorkflowStatus;
  schema_snapshot: JsonObject;
  graph_snapshot: JsonObject;
  publication_report: JsonObject;
  created_at: string;
  published_at: string | null;
};

export type VersionDiff = {
  from_version_id: string;
  to_version_id: string;
  schema: JsonObject;
  graph: JsonObject;
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

export type BuildContextVersionSummary = Pick<
  OntologyVersion,
  "status" | "workflow_status" | "version_number"
>;

export type BuildContextOntology = {
  id: string;
  name: string;
  status: string;
  current_version_id: string | null;
  current_version: BuildContextVersionSummary | null;
};

export type BuildContext = {
  project: Pick<Project, "id" | "name" | "description">;
  project_brief: ProjectBrief;
  ontologies: BuildContextOntology[];
  competency_question_counts: Record<string, number>;
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
  audit_id: string;
  applied: boolean;
  affected_graph_iris: string[];
  delta: SemanticJsonObject;
  warnings: string[];
  validation: SemanticJsonObject | null;
  graph_revisions: Record<string, number>;
  stale_derived_pointers: SemanticJsonObject[];
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

export type SemanticMissingEvidenceSummary = {
  graph_set_id: string;
  dependencies: SemanticJsonObject[];
  summary: SemanticJsonObject;
  warning: string | null;
};

export type SemanticStatementItem = {
  id: string;
  iri: string;
  label: string | null;
  source_graph_iri: string;
  assertion_kind: string;
  evidence_status: string;
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

export type SemanticSparqlQueryResponse = {
  result: unknown;
  result_format: string;
  truncated: boolean;
  warnings: string[];
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
export type SemanticEditEvidenceStatus = "evidence_bound" | "missing_evidence";
export type SemanticExportFormat = "trig" | "turtle" | "json-ld";
export type SemanticExportInclude =
  | "asserted"
  | "asserted-plus-reasoning"
  | "asserted-plus-rules"
  | "full-working-view";
