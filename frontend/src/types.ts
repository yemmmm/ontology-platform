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

export type SourceDocument = {
  id: string;
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

export type SourceChunk = {
  id: string;
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

export type ReviewBatchType = "schema" | "entity" | "relation" | "merge" | "conflict" | "fact";
export type ReviewBatchStatus = "pending" | "in_review" | "completed";

export type ReviewBatch = {
  id: string;
  stable_key: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string;
  review_type: ReviewBatchType;
  status: ReviewBatchStatus;
  item_ids: string[];
  counts: Record<string, number>;
  deep_link: string;
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
