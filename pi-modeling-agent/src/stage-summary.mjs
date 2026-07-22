// Stage Summary schema and validation. A summary is the only structured narrative a stage produces;
// it is built from that stage's bounded visible events and stable artifact references only.

export const SUMMARY_FIELDS = Object.freeze([
  "stage",
  "roles",
  "goal",
  "actions",
  "inputs_outputs",
  "issues_decisions",
  "result",
  "unresolved",
  "next_step",
]);

/** Field types used to reject non-scalar shapes that would smuggle in hidden reasoning. */
const FIELD_EXPECTATIONS = {
  stage: "string",
  goal: "string",
  result: "string",
  next_step: "string",
  roles: "array",
  actions: "array",
  inputs_outputs: "object",
  issues_decisions: "array",
  unresolved: "array",
};

export class SummaryValidationError extends Error {}

/**
 * Validate a stage summary. Rejects missing/extra fields and any field that would carry hidden
 * reasoning, a full transcript, raw source bodies, raw platform responses, or credentials.
 */
export function validateSummary(summary) {
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) {
    throw new SummaryValidationError("summary must be an object");
  }
  const keys = new Set(Object.keys(summary));
  for (const field of SUMMARY_FIELDS) {
    if (!keys.has(field)) {
      throw new SummaryValidationError(`summary missing field: ${field}`);
    }
  }
  const extra = [...keys].filter((field) => !SUMMARY_FIELDS.includes(field));
  if (extra.length) {
    throw new SummaryValidationError(`summary has extra fields: ${extra.join(", ")}`);
  }
  for (const [field, kind] of Object.entries(FIELD_EXPECTATIONS)) {
    const value = summary[field];
    const ok =
      kind === "array"
        ? Array.isArray(value)
        : kind === "object"
          ? value && typeof value === "object" && !Array.isArray(value)
          : typeof value === kind && String(value).trim().length > 0;
    if (!ok) {
      throw new SummaryValidationError(`summary field ${field} must be a non-empty ${kind}`);
    }
  }
  // inputs_outputs carries only bounded references; reject values that look like raw payloads.
  for (const [key, value] of Object.entries(summary.inputs_outputs)) {
    if (typeof key !== "string" || !key.trim()) {
      throw new SummaryValidationError("inputs_outputs keys must be non-empty strings");
    }
    if (value && typeof value === "object" && (value.transcript || value.reasoning || value.raw)) {
      throw new SummaryValidationError(
        `inputs_outputs.${key} must not carry transcript/reasoning/raw payloads`,
      );
    }
  }
  return true;
}

/** Select only the bounded event fields a summarizer is allowed to see for one stage. */
export function summarizeVisibleEvents(records) {
  const allowed = new Set([
    "agent_start",
    "agent_end",
    "agent_settled",
    "turn_start",
    "tool_execution_start",
    "tool_execution_end",
    "queue_update",
    "auto_retry",
    "compaction_start",
    "compaction_end",
    "extension_ui_request",
  ]);
  return records
    .filter((record) => allowed.has(record.type))
    .map((record) => ({
      type: record.type,
      tool: record.toolName ?? null,
      isError: record.isError ?? null,
      method: record.method ?? null,
      queueLength: record.length ?? (Array.isArray(record.queue) ? record.queue.length : null),
    }));
}
