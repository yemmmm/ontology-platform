import { API_BASE_URL, apiRequest } from "./api";
import type {
  SemanticDatasetLoadResponse,
  SemanticDerivedResultReconcileResponse,
  SemanticEditAuditRead,
  SemanticEditEvidenceStatus,
  SemanticEditInputFormat,
  SemanticEditResponse,
  SemanticExportFormat,
  SemanticExportInclude,
  SemanticGraphEditabilityResponse,
  SemanticGraphGcResponse,
  SemanticGraphRegistryListResponse,
  SemanticGraphRegistryRead,
  SemanticGraphSetListResponse,
  SemanticGraphSetRead,
  SemanticGovernanceStatusResponse,
  SemanticJsonObject,
  SemanticMissingEvidenceSummary,
  SemanticProjectionJobListResponse,
  SemanticProjectionJobRead,
  SemanticReadModelEnvelope,
  SemanticRuleDefinitionListResponse,
  SemanticRuleDefinitionRead,
  SemanticRuleRunRead,
  SemanticSparqlQueryResponse,
  SemanticValidationRunRead,
  SemanticReasoningRunRead,
} from "./types";

export type SemanticRequester = <T,>(path: string, options?: RequestInit) => Promise<T>;

const SEMANTIC_BASE = "/semantic";

function withParams(base: string, params: Record<string, unknown> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const suffix = search.toString();
  return suffix ? `${base}?${suffix}` : base;
}

export function getGovernanceStatus(request: SemanticRequester) {
  return request<SemanticGovernanceStatusResponse>(`${SEMANTIC_BASE}/status`);
}

export function listGraphRegistry(
  request: SemanticRequester,
  filters: { category?: string; ownerType?: string; ownerId?: string; includeRevisions?: boolean } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/graphs`, {
    category: filters.category,
    owner_type: filters.ownerType,
    owner_id: filters.ownerId,
    include_revisions: filters.includeRevisions,
  });
  return request<SemanticGraphRegistryListResponse>(path);
}

export function getGraphRegistry(request: SemanticRequester, graphIri: string) {
  return request<SemanticGraphRegistryRead>(`${SEMANTIC_BASE}/graphs/${graphIri}`);
}

export function updateGraphEditability(
  request: SemanticRequester,
  graphIri: string,
  editable: boolean,
  actor?: string,
  reason?: string,
) {
  return request<SemanticGraphEditabilityResponse>(
    `${SEMANTIC_BASE}/graphs/${graphIri}/editability`,
    {
      method: "PATCH",
      body: JSON.stringify({ editable, actor, reason }),
    },
  );
}

export function listGraphSets(
  request: SemanticRequester,
  filters: { scopeType?: string; scopeId?: string; status?: string } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/graph-sets`, filters);
  return request<SemanticGraphSetListResponse>(path);
}

export function getGraphSet(request: SemanticRequester, graphSetId: string) {
  return request<SemanticGraphSetRead>(`${SEMANTIC_BASE}/graph-sets/${graphSetId}`);
}

export function createGraphSet(
  request: SemanticRequester,
  payload: {
    name: string;
    scopeType: string;
    scopeId?: string | null;
    members: Array<{
      graph_iri: string;
      role: string;
      required?: boolean;
      sort_order?: number;
      metadata?: SemanticJsonObject;
    }>;
    createdBy?: string;
    supersedes?: string;
    metadata?: SemanticJsonObject;
  },
) {
  return request<SemanticGraphSetRead>(`${SEMANTIC_BASE}/graph-sets`, {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      scope_type: payload.scopeType,
      scope_id: payload.scopeId ?? null,
      members: payload.members,
      created_by: payload.createdBy,
      supersedes: payload.supersedes,
      metadata: payload.metadata ?? {},
    }),
  });
}

export function updateGraphSetMembers(
  request: SemanticRequester,
  graphSetId: string,
  members: Array<{
    graph_iri: string;
    role: string;
    required?: boolean;
    sort_order?: number;
    metadata?: SemanticJsonObject;
  }>,
) {
  return request<SemanticGraphSetRead>(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/members`,
    {
      method: "PUT",
      body: JSON.stringify({ members }),
    },
  );
}

export function listEditAudits(request: SemanticRequester, limit = 25) {
  const path = withParams(`${SEMANTIC_BASE}/edits/audits`, { limit });
  return request<SemanticEditAuditRead[]>(path);
}

export function previewSemanticEdit(
  request: SemanticRequester,
  payload: {
    format: SemanticEditInputFormat;
    content: string;
    targetGraphIri?: string;
    shapeGraphIris?: string[];
    actor?: string;
    reason?: string;
    evidenceStatus?: SemanticEditEvidenceStatus | null;
    warningState?: SemanticJsonObject;
  },
) {
  return request<SemanticEditResponse>(`${SEMANTIC_BASE}/edits`, {
    method: "POST",
    body: JSON.stringify({
      format: payload.format,
      content: payload.content,
      target_graph_iri: payload.targetGraphIri,
      validate: false,
      shape_graph_iris: payload.shapeGraphIris ?? [],
      actor: payload.actor,
      reason: payload.reason,
      evidence_status: payload.evidenceStatus ?? undefined,
      warning_state: payload.warningState ?? {},
    }),
  });
}

export function applySemanticEdit(
  request: SemanticRequester,
  payload: {
    format: SemanticEditInputFormat;
    content: string;
    targetGraphIri?: string;
    shapeGraphIris?: string[];
    actor?: string;
    reason?: string;
    evidenceStatus?: SemanticEditEvidenceStatus | null;
    warningState?: SemanticJsonObject;
  },
) {
  return request<SemanticEditResponse>(`${SEMANTIC_BASE}/edits`, {
    method: "POST",
    body: JSON.stringify({
      format: payload.format,
      content: payload.content,
      target_graph_iri: payload.targetGraphIri,
      validate: true,
      shape_graph_iris: payload.shapeGraphIris ?? [],
      actor: payload.actor,
      reason: payload.reason,
      evidence_status: payload.evidenceStatus ?? undefined,
      warning_state: payload.warningState ?? {},
    }),
  });
}

export function runGraphSetValidation(
  request: SemanticRequester,
  graphSetId: string,
  payload: {
    shapeGraphIris?: string[];
    inference?: string;
    validationScope?: "asserted_only" | "asserted_plus_reasoning";
    reasoningResultGraphIri?: string;
    shapeVersion?: string;
    engineVersion?: string;
    persistReportGraph?: boolean;
    actor?: string;
  } = {},
) {
  return request<{ run_id: string; status: string; conforms: boolean | null; summary: SemanticJsonObject; error: string | null }>(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/validation-runs`,
    {
      method: "POST",
      body: JSON.stringify({
        shape_graph_iris: payload.shapeGraphIris ?? [],
        inference: payload.inference,
        validation_scope: payload.validationScope ?? "asserted_only",
        reasoning_result_graph_iri: payload.reasoningResultGraphIri,
        shape_version: payload.shapeVersion,
        engine_version: payload.engineVersion,
        persist_report_graph: payload.persistReportGraph ?? true,
        actor: payload.actor,
      }),
    },
  );
}

export function runGraphSetReasoning(
  request: SemanticRequester,
  graphSetId: string,
  payload: { tasks?: string[]; engineVersion?: string; shapeVersion?: string; persistResultGraph?: boolean } = {},
) {
  return request<{ run_id: string; status: string; consistent: boolean | null; classification: SemanticJsonObject; entailments: SemanticJsonObject[]; result_graph_iri: string | null; derived_pointer: SemanticJsonObject | null; error: string | null }>(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/reasoning-runs`,
    {
      method: "POST",
      body: JSON.stringify({
        tasks: payload.tasks ?? ["consistency"],
        persist_result_graph: payload.persistResultGraph ?? true,
        engine_version: payload.engineVersion,
        shape_version: payload.shapeVersion,
      }),
    },
  );
}

export function runGraphSetRules(
  request: SemanticRequester,
  graphSetId: string,
  payload: { ruleDefinitionIds?: string[]; ruleDefinitionId?: string; ruleIri?: string; engineVersion?: string; promotePointer?: boolean; actor?: string } = {},
) {
  return request<SemanticRuleRunRead>(`${SEMANTIC_BASE}/graph-sets/${graphSetId}/rule-runs`, {
    method: "POST",
    body: JSON.stringify({
      rule_definition_ids: payload.ruleDefinitionIds,
      rule_definition_id: payload.ruleDefinitionId,
      rule_iri: payload.ruleIri,
      engine_version: payload.engineVersion,
      promote_pointer: payload.promotePointer ?? true,
      actor: payload.actor,
    }),
  });
}

export function getValidationRun(request: SemanticRequester, runId: string) {
  return request<SemanticValidationRunRead>(`${SEMANTIC_BASE}/validation-runs/${runId}`);
}

export function getReasoningRun(request: SemanticRequester, runId: string) {
  return request<SemanticReasoningRunRead>(`${SEMANTIC_BASE}/reasoning-runs/${runId}`);
}

export function getRuleRun(request: SemanticRequester, runId: string) {
  return request<SemanticRuleRunRead>(`${SEMANTIC_BASE}/rule-runs/${runId}`);
}

export function listRuleDefinitions(
  request: SemanticRequester,
  filters: { status?: string; language?: string; ruleIri?: string; limit?: number } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/rule-definitions`, filters);
  return request<SemanticRuleDefinitionListResponse>(path);
}

export function createRuleDefinition(
  request: SemanticRequester,
  payload: {
    ruleIri: string;
    name: string;
    language: "sparql_construct" | "platform_dsl" | "workflow_state_machine";
    body: SemanticJsonObject;
    inputRoles?: string[];
    outputKind?: "assertion" | "validation" | "workflow" | "annotation";
    usesInferredFacts?: boolean;
    requiresReview?: boolean;
    priority?: number;
    safetyProfile?: SemanticJsonObject;
    status?: "draft" | "active" | "retired" | "rejected";
    createdBy?: string;
    metadata?: SemanticJsonObject;
  },
) {
  return request<SemanticRuleDefinitionRead>(`${SEMANTIC_BASE}/rule-definitions`, {
    method: "POST",
    body: JSON.stringify({
      rule_iri: payload.ruleIri,
      name: payload.name,
      language: payload.language,
      body: payload.body,
      input_roles: payload.inputRoles ?? [],
      output_kind: payload.outputKind ?? "assertion",
      uses_inferred_facts: payload.usesInferredFacts ?? false,
      requires_review: payload.requiresReview ?? false,
      priority: payload.priority ?? 0,
      safety_profile: payload.safetyProfile ?? {},
      status: payload.status ?? "draft",
      created_by: payload.createdBy,
      metadata: payload.metadata ?? {},
    }),
  });
}

export function getMissingEvidenceSummary(request: SemanticRequester, graphSetId: string) {
  return request<SemanticMissingEvidenceSummary>(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/missing-evidence`,
  );
}

export function reconcileDerivedResults(request: SemanticRequester) {
  return request<SemanticDerivedResultReconcileResponse>(`${SEMANTIC_BASE}/derived-results:reconcile`, {
    method: "POST",
  });
}

export function runDerivedResultsGc(request: SemanticRequester, targetKind = "reasoning_result", dryRun = false) {
  return request<SemanticGraphGcResponse>(`${SEMANTIC_BASE}/derived-results:gc`, {
    method: "POST",
    body: JSON.stringify({ target_kind: targetKind, dry_run: dryRun }),
  });
}

export function listStatements(
  request: SemanticRequester,
  payload: { graphSetId: string; include?: SemanticExportInclude; allowStaleDerived?: boolean; limit?: number },
) {
  const path = withParams(`${SEMANTIC_BASE}/statements`, {
    graph_set_id: payload.graphSetId,
    include: payload.include ?? "asserted",
    allow_stale_derived: payload.allowStaleDerived ?? true,
    limit: payload.limit,
  });
  return request<SemanticReadModelEnvelope>(path);
}

// Stage 2 §3.2 — read-model fetchers ----------------------------------------

export function readModel<T = SemanticReadModelEnvelope>(
  request: SemanticRequester,
  graphSetId: string,
  modelName: string,
  params: {
    include?: string;
    fieldSet?: string;
    limit?: number;
    /** Stage 2 §6.3 fact-audit-queue composer: drives source-graph selection
     * (asserted / inferred / rule_derived / missing_evidence). */
    kind?: string;
    /** Stage 3 §4.3 graph-set-delta composer: the other graph set id to
     * diff against (passed as the `target` query param). */
    target?: string;
  } = {},
) {
  const path = withParams(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/read-models/${modelName}`,
    {
      include: params.include ?? "asserted",
      field_set: params.fieldSet ?? "summary",
      limit: params.limit,
      kind: params.kind,
      target: params.target,
    },
  );
  return request<T>(path);
}

// Stage 2 §3.4 — per-class shape guidance -----------------------------------

export type SemanticShaclFieldConstraint = {
  path?: string;
  name?: string;
  label?: string;
  datatype?: string;
  class_iri?: string;
  min_count?: number;
  max_count?: number;
  pattern?: string;
  enumeration?: unknown[];
  description?: string;
  required?: boolean;
  provenance?: "generated" | "custom" | "merged";
};

export type SemanticShaclFormGuidance = {
  target_class?: string;
  target_class_label?: string;
  shape_iri?: string;
  fields?: SemanticShaclFieldConstraint[];
  graph_set_id?: string;
  generated_graph_iri?: string;
  custom_graph_iri?: string;
  shape_split?: { generated_subgraph: string; custom_subgraph: string };
};

export function getClassShapeGuidance(
  request: SemanticRequester,
  graphSetId: string,
  classIri: string,
) {
  return request<SemanticShaclFormGuidance>(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/shapes/classes/${classIri}`,
  );
}

// Stage 2 §3.3 — canonical-write dispatcher ---------------------------------

export type SemanticCanonicalWriteResult = {
  applied: boolean;
  graph_revisions?: Record<string, number>;
  validation_report?: unknown;
  delta?: unknown;
};

export function compileAndApplyProductCommand(
  request: SemanticRequester,
  payload: {
    command_kind: string;
    payload: Record<string, unknown>;
    graph_set_id: string;
    actor?: string;
    reason?: string;
    validate_edit?: boolean;
  },
) {
  return request<SemanticCanonicalWriteResult>(
    `${SEMANTIC_BASE}/canonical-writes:compile-and-apply`,
    {
      method: "POST",
      body: JSON.stringify({
        command_kind: payload.command_kind,
        payload: payload.payload,
        graph_set_id: payload.graph_set_id,
        actor: payload.actor,
        reason: payload.reason,
        validate_edit: payload.validate_edit ?? false,
      }),
    },
  );
}

export function sparqlQuery(
  request: SemanticRequester,
  payload: { query: string; timeoutSeconds?: number; resultLimit?: number },
) {
  return request<SemanticSparqlQueryResponse>(`${SEMANTIC_BASE}/sparql:query`, {
    method: "POST",
    body: JSON.stringify({
      query: payload.query,
      timeout_seconds: payload.timeoutSeconds,
      result_limit: payload.resultLimit,
    }),
  });
}

export function loadDataset(
  request: SemanticRequester,
  payload: { content: string; format: "trig" | "turtle" | "json-ld"; baseIri?: string },
) {
  return request<SemanticDatasetLoadResponse>(`${SEMANTIC_BASE}/datasets:load`, {
    method: "POST",
    body: JSON.stringify({
      content: payload.content,
      format: payload.format,
      base_iri: payload.baseIri,
    }),
  });
}

export function buildGraphSetExportUrl(
  graphSetId: string,
  payload: {
    format: SemanticExportFormat;
    include: SemanticExportInclude;
    includeEvidence?: boolean;
    includeShapes?: boolean;
    includePolicy?: boolean;
    includeMetadata?: boolean;
    allowStaleDerived?: boolean;
  },
): string {
  const params = new URLSearchParams({
    format: payload.format,
    include: payload.include,
  });
  if (payload.includeEvidence) params.set("include_evidence", "true");
  if (payload.includeShapes) params.set("include_shapes", "true");
  if (payload.includePolicy) params.set("include_policy", "true");
  if (payload.includeMetadata) params.set("include_metadata", "true");
  if (payload.allowStaleDerived) params.set("allow_stale_derived", "true");
  return `${API_BASE_URL}${SEMANTIC_BASE}/graph-sets/${graphSetId}/export?${params.toString()}`;
}

export function listProjectionJobs(
  request: SemanticRequester,
  filters: { graphSetId?: string; projectionKind?: string; status?: string } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/projection-jobs`, filters);
  return request<SemanticProjectionJobListResponse>(path);
}

export function getProjectionJob(request: SemanticRequester, jobId: string) {
  return request<SemanticProjectionJobRead>(`${SEMANTIC_BASE}/projection-jobs/${jobId}`);
}

export function runProjectionJob(request: SemanticRequester, jobId: string) {
  return request<SemanticProjectionJobRead>(`${SEMANTIC_BASE}/projection-jobs/${jobId}:run`, {
    method: "POST",
  });
}

export { SEMANTIC_BASE };
