export type WorkbenchRequest = <T>(path: string, options?: globalThis.RequestInit) => Promise<T>;

export type WorkbenchNavigate = (tab: string, params?: Record<string, string>) => void;

export type BuildContext = {
  project: { id: string; name: string; description: string | null };
  project_brief: ProjectBrief;
  ontologies: Array<{
    id: string;
    name: string;
    status: string;
    current_version_id: string | null;
    current_version: {
      status: string;
      workflow_status: string;
      version_number: number;
    } | null;
  }>;
  competency_question_counts: Record<string, number>;
};

export type ProjectBrief = {
  id: string | null;
  project_id: string;
  fields: Record<string, unknown>;
  field_states: Record<string, string>;
  field_sources: Record<string, string[]>;
  missing_fields: string[];
  clarification_items: Array<{ field: string; question: string; reason: string }>;
  completeness: number;
};

export type CompetencyQuestion = {
  id: string;
  project_id: string;
  ontology_id: string;
  question: string;
  importance: number;
  position: number;
  status: string;
  active: boolean;
  query_definition: Record<string, unknown>;
  validation_result: Record<string, unknown>;
  source_answer_ids: string[];
  source_brief_fields: string[];
  created_at: string;
  updated_at: string;
};

export type OntologyVersionSummary = {
  id: string;
  ontology_id: string;
  parent_version_id: string | null;
  version_number: number;
  status: string;
  workflow_status: string;
  created_at: string;
  published_at: string | null;
};

export type ProposalSummary = {
  id: string;
  project_id: string;
  ontology_id: string;
  target_version_id: string;
  proposal_type: string;
  status: string;
  created_at: string;
  updated_at: string;
};
