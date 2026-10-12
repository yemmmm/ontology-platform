export type JsonObject = Record<string, unknown>;
export type Project = { id: string; name: string; description?: string | null };
export type Ontology = { id: string; name: string };
export type Artifact = {
  artifact_id: string; kind: string; availability: string;
  source: { path?: string; updated_at?: string }; scope: JsonObject;
  limitations: string[]; data: JsonObject;
};
export type RunSummary = { run_id: string; state: string | JsonObject; source_updated_at: string };
export type RunIndex = { current_run_id: string | null; runs: RunSummary[]; completeness: { complete: boolean }; observed_at: string };
export type Run = { run_id: string; state: string | JsonObject; observed_at: string; current_questions_available?: boolean; acceptance_reports_complete?: boolean; artifacts: Record<string, Artifact[]> };
export type Resource = {
  id?: string; iri: string; label?: string | null; description?: string;
  kind?: string; type_iri?: string; ontology_id?: string;
  detail_fields?: JsonObject; properties?: JsonObject; data?: JsonObject;
};
export type Relation = { id: string; source: string; target: string; relation: string; label?: string; assertion_kind: string; edge_kind?: "rdf_relation" | "structured_reference"; field_path?: string };
export type Envelope<T> = { items: T[]; model_revision: number; paging?: { complete?: boolean }; warnings?: { code?: string; message?: string }[] };
export type RecallResult = Resource & { id: string };
export type SemanticContextQueryRequest = {
  project_id: string; scope_mode: "project" | "ontologies"; ontology_ids?: string[];
  query?: string; queries?: string[]; resource_types?: string[]; assertion_types?: string[];
  semantic_roles?: string[]; search_mode?: "hybrid" | "lexical"; depth?: number;
  limit?: number; context_limit?: number; context_detail?: "full" | "compact" | "preview";
  match_cursor?: string; context_cursor?: string;
};
export type RecallResponse = {
  query?: JsonObject; scope?: JsonObject; related_context?: JsonObject[];
  context_page?: JsonObject; truncated?: boolean;
  primary_matches: RecallResult[]; result_status: string;
  matches_page: JsonObject & { next_match_cursor?: string | null; complete?: boolean; has_more?: boolean };
  recall: JsonObject & { completeness?: string }; warnings: { code?: string; message?: string }[];
};
export type SemanticFeedbackReason = "incomplete" | "incorrect" | "irrelevant" | "other";
export type SemanticFeedbackRequest = {
  feedback_id: string; query_request: SemanticContextQueryRequest;
  reasons: SemanticFeedbackReason[]; description: string;
  result_snapshot?: JsonObject; snapshot_complete: boolean;
};
export type SemanticFeedbackReceipt = { feedback_id: string; received_at: string; status: "received" };
export type AccessRole = { id: string; name: string; description?: string | null; grants: string[] };
export const semanticViews = [
  ["object", "Object"], ["behavior", "Behavior"], ["rule", "Rule"], ["business_role", "Business role"],
  ["process", "Process"], ["data_mapping", "Data mapping"], ["interface_mapping", "Interface mapping"],
] as const;
export type ConversationMessage = {
  message_id: string; kind: string; text: string;
  sender?: { kind: string; reference: string }; entrypoint?: string;
  submitted_by?: { kind: string; reference: string };
  recorded_at?: string; received_seq?: number; dispatch?: string; dispatch_reason?: string;
  control?: { action: string; status: string; basis?: unknown };
  reply_to_message_id?: string | null; reply_to_message_ids?: string[];
};
export type ConversationEvent = {
  event_seq: number; event_type: string; recorded_at: string; message_id?: string;
  message?: ConversationMessage; status?: string; action?: string; basis?: unknown;
};
export type ConversationIndex = {
  items: { delivery_session_id: string; history_started_at: string | null; history_complete: boolean }[];
  enumeration_complete: boolean;
};
export type ConversationStatus = {
  delivery_session_id: string; connection: "online" | "offline" | "unknown";
  activity: string; observed_at: string | null; history_started_at: string | null;
  pending_questions: ConversationMessage[]; latest_event_seq: number;
  basis?: unknown;
  history_complete: boolean; read_error?: string; delivery_result?: string;
};
export type ConversationInput = {
  message_id: string; kind: "message" | "answer" | "control"; text: string;
  reply_to_message_id?: string; action?: "pause" | "resume" | "cancel" | "revoke_budget" | "stop";
};
export type ConversationEvents = {
  items: ConversationEvent[]; next_after_seq: number; has_more: boolean;
  history_complete: boolean; read_error?: string;
};
