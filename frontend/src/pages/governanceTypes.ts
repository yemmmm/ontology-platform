import type { Ontology, Project } from "../types";

export type Requester = <T>(path: string, options?: RequestInit) => Promise<T>;

export type OntologyVersion = {
  id: string;
  ontology_id: string;
  parent_version_id: string | null;
  version_number: number;
  status: string;
  workflow_status: string;
  schema_snapshot: Record<string, unknown>;
  graph_snapshot: Record<string, unknown>;
  publication_report: Record<string, unknown>;
  created_at: string;
  published_at: string | null;
};

export type GovernancePageContext = {
  project: Project;
  ontology: Ontology;
  version: OntologyVersion;
  request: Requester;
  readOnly?: boolean;
  onNavigate?: (tab: string, params?: Record<string, string>) => void;
};

export function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

export function jsonText(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
