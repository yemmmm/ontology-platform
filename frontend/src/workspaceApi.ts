import { apiRequest } from "./api";
import type { ConversationIndex, ConversationStatus, ConversationEvents, ConversationMessage, ConversationInput } from "./workspaceTypes";

const conversationPath = (project: string, session?: string) => `/projects/${encodeURIComponent(project)}/delivery-conversations${session ? `/${encodeURIComponent(session)}` : ""}`;
import type { AccessRole, Envelope, Ontology, Project, RecallResponse, Relation, Resource, Run, RunIndex, SemanticContextQueryRequest, SemanticFeedbackRequest, SemanticFeedbackReceipt } from "./workspaceTypes";
export const workspaceApi = {
  conversations: (project: string) => apiRequest<ConversationIndex>(conversationPath(project)),
  conversation: (project: string, session: string) => apiRequest<ConversationStatus>(conversationPath(project, session)),
  conversationEvents: (project: string, session: string, cursor: number) => apiRequest<ConversationEvents>(`${conversationPath(project, session)}/events?after_seq=${cursor}&limit=100`),
  conversationReceipt: (project: string, session: string, message: string) => apiRequest<ConversationMessage>(`${conversationPath(project, session)}/messages/${encodeURIComponent(message)}`),
  conversationSend: (project: string, session: string, message: ConversationInput) => apiRequest<{ message: ConversationMessage; created: boolean }>(`${conversationPath(project, session)}/messages`, { method: "POST", body: JSON.stringify(message) }),
  projects: () => apiRequest<Project[]>("/projects"),
  index: (project: string) => apiRequest<RunIndex>(`/projects/${encodeURIComponent(project)}/workbench`),
  run: (project: string, run: string) => apiRequest<Run>(`/projects/${encodeURIComponent(project)}/workbench/runs/${encodeURIComponent(run)}`),
  questions: (project: string, run: string) => apiRequest<Run>(`/projects/${encodeURIComponent(project)}/workbench/runs/${encodeURIComponent(run)}/competency-questions`),
  ontologies: (project: string) => apiRequest<Ontology[]>(`/projects/${encodeURIComponent(project)}/ontologies`),
  workspace: (ontology: string) => apiRequest<{ ontology_id: string; state: "ready" | "incomplete" }>(`/ontologies/${encodeURIComponent(ontology)}/workspace-context`),
  resources: (ontology: string) => apiRequest<Envelope<Resource>>(`/semantic/ontologies/${encodeURIComponent(ontology)}/read-models/resource-list?include=asserted&field_set=detail&limit=500`),
  relations: (ontology: string) => apiRequest<Envelope<Relation>>(`/semantic/ontologies/${encodeURIComponent(ontology)}/read-models/resource-relations?include=asserted&limit=1000`),
  roles: (project: string) => apiRequest<AccessRole[]>(`/projects/${encodeURIComponent(project)}/semantic-access-roles`),
  recall: (request: SemanticContextQueryRequest) => apiRequest<RecallResponse>("/semantic/context:query", { method: "POST", body: JSON.stringify(request) }),
  submitSemanticFeedback: (request: SemanticFeedbackRequest) => apiRequest<SemanticFeedbackReceipt>("/semantic/feedback", { method: "POST", body: JSON.stringify(request) }),
};
