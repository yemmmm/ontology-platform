import { API_BASE_URL, apiRequest } from "./api";
import type {
  FactEvidenceBinding,
  MissingEvidenceFactsResponse,
  SemanticDerivedResultReconcileResponse,
  SemanticEditAuditRead,
  SemanticExportFormat,
  SemanticExportInclude,
  SemanticGraphRegistryListResponse,
  SemanticGraphSetListResponse,
  SemanticGraphSetRead,
  SemanticGovernanceStatusResponse,
  SemanticJsonObject,
  SemanticProjectionStatusResponse,
  SemanticReadModelEnvelope,
  SemanticReasoningRunListResponse,
  SemanticRuleDefinitionListResponse,
  SemanticRuleDefinitionRead,
  SemanticRuleRunListResponse,
  SemanticRuleRunRead,
  SemanticValidationRunListResponse,
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

export function listGraphSets(
  request: SemanticRequester,
  filters: { scopeType?: string; scopeId?: string; status?: string } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/graph-sets`, {
    scope_type: filters.scopeType,
    scope_id: filters.scopeId,
    status: filters.status,
  });
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

export function listValidationRuns(
  request: SemanticRequester,
  filters: { graphSetId?: string; kind?: string; limit?: number; offset?: number } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/validation-runs`, {
    graph_set_id: filters.graphSetId,
    kind: filters.kind,
    limit: filters.limit,
    offset: filters.offset,
  });
  return request<SemanticValidationRunListResponse>(path);
}

export function getReasoningRun(request: SemanticRequester, runId: string) {
  return request<SemanticReasoningRunRead>(`${SEMANTIC_BASE}/reasoning-runs/${runId}`);
}

export function listReasoningRuns(
  request: SemanticRequester,
  filters: { graphSetId?: string; kind?: string; limit?: number; offset?: number } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/reasoning-runs`, {
    graph_set_id: filters.graphSetId,
    kind: filters.kind,
    limit: filters.limit,
    offset: filters.offset,
  });
  return request<SemanticReasoningRunListResponse>(path);
}

export function getRuleRun(request: SemanticRequester, runId: string) {
  return request<SemanticRuleRunRead>(`${SEMANTIC_BASE}/rule-runs/${runId}`);
}

export function listRuleRuns(
  request: SemanticRequester,
  filters: { graphSetId?: string; kind?: string; limit?: number; offset?: number } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/rule-runs`, {
    graph_set_id: filters.graphSetId,
    kind: filters.kind,
    limit: filters.limit,
    offset: filters.offset,
  });
  return request<SemanticRuleRunListResponse>(path);
}

export function listRuleDefinitions(
  request: SemanticRequester,
  filters: {
    language?: string;
    ruleIri?: string;
    ontologyId?: string;
    currentOnly?: boolean;
    limit?: number;
  } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/rule-definitions`, {
    language: filters.language,
    rule_iri: filters.ruleIri,
    ontology_id: filters.ontologyId,
    current_only: filters.currentOnly,
    limit: filters.limit,
  });
  return request<SemanticRuleDefinitionListResponse>(path);
}

export function createRuleDefinition(
  request: SemanticRequester,
  payload: {
    ontologyId: string;
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
    createdBy?: string;
    metadata?: SemanticJsonObject;
  },
) {
  return request<SemanticRuleDefinitionRead>(`${SEMANTIC_BASE}/rule-definitions`, {
    method: "POST",
    body: JSON.stringify({
      ontology_id: payload.ontologyId,
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
      created_by: payload.createdBy,
      metadata: payload.metadata ?? {},
    }),
  });
}

export function updateRuleDefinition(
  request: SemanticRequester,
  ruleId: string,
  payload: {
    name?: string;
    priority?: number;
    metadata?: SemanticJsonObject;
  },
) {
  return request<SemanticRuleDefinitionRead>(`${SEMANTIC_BASE}/rule-definitions/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: payload.name,
      priority: payload.priority,
      metadata: payload.metadata,
    }),
  });
}

export function deleteRuleDefinition(request: SemanticRequester, ruleId: string) {
  return request<void>(`${SEMANTIC_BASE}/rule-definitions/${ruleId}`, {
    method: "DELETE",
  });
}

/**
 * Phase 8 §3 — bind a free-text evidence chunk to a fact via the new
 * ``POST /api/semantic/graph-sets/{gs}/fact-evidence`` endpoint. The
 * returned ``FactEvidenceBinding`` is the persisted binding record.
 *
 * The ``ontology_id`` plus subject/predicate/object triple uniquely
 * identify the target fact; ``text`` carries the human-readable evidence
 * snippet. ``actor`` defaults to a sentinel value when the caller does
 * not supply one (matching the legacy command-path behavior).
 */
export function bindFactEvidence(
  request: SemanticRequester,
  graphSetId: string,
  payload: {
    ontology_id: string;
    subject_iri: string;
    predicate_iri: string;
    object_value: string;
    object_is_iri?: boolean;
    object_datatype?: string;
    object_lang?: string;
    graph_iri?: string;
    fact_id?: string;
    assertion_kind?: string;
    chunk_id?: string;
    evidence_artifact_id?: string;
    evidence_reference_id?: string;
    document_filename?: string;
    sequence?: number;
    char_start?: number;
    char_end?: number;
    text: string;
    actor?: string;
    reason?: string;
  },
) {
  return request<FactEvidenceBinding>(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/fact-evidence`,
    {
      method: "POST",
      body: JSON.stringify({
        ontology_id: payload.ontology_id,
        subject_iri: payload.subject_iri,
        predicate_iri: payload.predicate_iri,
        object_value: payload.object_value,
        object_is_iri: payload.object_is_iri,
        object_datatype: payload.object_datatype,
        object_lang: payload.object_lang,
        graph_iri: payload.graph_iri,
        fact_id: payload.fact_id,
        assertion_kind: payload.assertion_kind,
        chunk_id: payload.chunk_id,
        evidence_artifact_id: payload.evidence_artifact_id,
        evidence_reference_id: payload.evidence_reference_id,
        document_filename: payload.document_filename,
        sequence: payload.sequence,
        char_start: payload.char_start,
        char_end: payload.char_end,
        text: payload.text,
        actor: payload.actor,
        reason: payload.reason,
      }),
    },
  );
}

/**
 * Phase 8 §3 — remove a fact↔evidence binding by its ``binding.id``.
 * The DELETE endpoint is idempotent and returns 204 on success.
 */
export function unbindFactEvidence(
  request: SemanticRequester,
  graphSetId: string,
  bindingId: string,
) {
  return request<void>(
    `${SEMANTIC_BASE}/graph-sets/${graphSetId}/fact-evidence/${encodeURIComponent(bindingId)}`,
    { method: "DELETE" },
  );
}

/**
 * Phase 8 §3 — list the fact IDs that currently lack any evidence binding,
 * backed by the Postgres-backed count on the backend. Optional ``limit``
 * caps the returned ID list (the ``count`` field reflects the unbounded
 * total).
 */
export function getMissingEvidenceFacts(
  request: SemanticRequester,
  graphSetId: string,
  limit?: number,
) {
  const path = withParams(`${SEMANTIC_BASE}/graph-sets/${graphSetId}/missing-evidence-facts`, {
    limit,
  });
  return request<MissingEvidenceFactsResponse>(path);
}

export function reconcileDerivedResults(request: SemanticRequester) {
  return request<SemanticDerivedResultReconcileResponse>(`${SEMANTIC_BASE}/derived-results:reconcile`, {
    method: "POST",
  });
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
     * (asserted / inferred / rule_derived). */
    kind?: string;
    /** Stage 3 §4.3 graph-set-delta composer: the other graph set id to
     * diff against (passed as the `target` query param). */
    target?: string;
    /** Stage 4 §4.1 entity-search composer: free-text search query string. */
    q?: string;
    /** Stage 4 §4.1 entity-search composer: restrict to a specific class IRI. */
    classIri?: string;
    /** Entity-scoped read models such as entity-literal-facts. */
    entity?: string;
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
      q: params.q,
      class_iri: params.classIri,
      entity: params.entity,
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

export function getProjectionStatus(
  request: SemanticRequester,
  filters: { graphSetId?: string } = {},
) {
  const path = withParams(`${SEMANTIC_BASE}/projections/status`, {
    graph_set_id: filters.graphSetId,
  });
  return request<SemanticProjectionStatusResponse>(path);
}

export { SEMANTIC_BASE };
