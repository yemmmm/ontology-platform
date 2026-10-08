import { apiRequest } from "./api";
import type { AccessRole, Envelope, Ontology, Project, RecallResponse, Relation, Resource, Run, RunIndex } from "./workspaceTypes";
export const workspaceApi = {
  projects: () => apiRequest<Project[]>("/projects"),
  index: (project: string) => apiRequest<RunIndex>(`/projects/${encodeURIComponent(project)}/workbench`),
  run: (project: string, run: string) => apiRequest<Run>(`/projects/${encodeURIComponent(project)}/workbench/runs/${encodeURIComponent(run)}`),
  questions: (project: string, run: string) => apiRequest<Run>(`/projects/${encodeURIComponent(project)}/workbench/runs/${encodeURIComponent(run)}/competency-questions`),
  ontologies: (project: string) => apiRequest<Ontology[]>(`/projects/${encodeURIComponent(project)}/ontologies`),
  workspace: (ontology: string) => apiRequest<{ ontology_id: string; state: "ready" | "incomplete" }>(`/ontologies/${encodeURIComponent(ontology)}/workspace-context`),
  resources: (ontology: string) => apiRequest<Envelope<Resource>>(`/semantic/ontologies/${encodeURIComponent(ontology)}/read-models/resource-list?include=asserted&field_set=detail&limit=500`),
  relations: (ontology: string) => apiRequest<Envelope<Relation>>(`/semantic/ontologies/${encodeURIComponent(ontology)}/read-models/resource-relations?include=asserted&limit=1000`),
  roles: (project: string) => apiRequest<AccessRole[]>(`/projects/${encodeURIComponent(project)}/semantic-access-roles`),
  recall: (project: string, query: string, cursor?: string) => apiRequest<RecallResponse>("/semantic/context:query", { method: "POST", body: JSON.stringify({
    project_id: project, scope_mode: "project", query,
    resource_types: ["concept", "instance", "operation", "mapping", "metric"], assertion_types: ["asserted"],
    search_mode: "hybrid", depth: 0, limit: 20, context_limit: 0, context_detail: "compact",
    ...(cursor ? { match_cursor: cursor } : {}),
  }) }),
};
