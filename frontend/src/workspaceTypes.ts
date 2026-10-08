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
export type Envelope<T> = { items: T[]; source_signature: string; paging?: { complete?: boolean }; warnings?: { code?: string; message?: string }[] };
export type RecallResult = Resource & { id: string };
export type RecallResponse = {
  primary_matches: RecallResult[]; result_status: string;
  matches_page: { next_match_cursor?: string | null; complete?: boolean; has_more?: boolean };
  recall: { completeness?: string }; warnings: { code?: string; message?: string }[];
};
export type AccessRole = { id: string; name: string; description?: string | null; grants: string[] };
export const semanticViews = [
  ["object", "Object"], ["behavior", "Behavior"], ["rule", "Rule"], ["business_role", "Business role"],
  ["process", "Process"], ["data_mapping", "Data mapping"], ["interface_mapping", "Interface mapping"],
] as const;
