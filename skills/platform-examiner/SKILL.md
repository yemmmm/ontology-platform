---
name: platform-examiner
description: Read-only, ticket-scoped semantic retrieval over modeled facts via the generic semantic query interface.
---

# Platform Examiner

This Skill is a generic semantic retrieval contract, not a business answer key.  The Runner
supplies the question, Project/Ontology/graph scope, model-state envelope, and the semantic
query tool.

- Use only the ticket-bound read shim and `query_semantic_context`.  Never use a write,
  validation-start, reasoning-start, key, Project, Ontology, or Lease operation, and never
  read modeling context, build sessions, read models, projections, validation/reasoning run
  internals, or evidence internals.
- Bind every request and response to the exact ticket Project, Ontology, graph set, and
  model-state digest.  Reject an omitted or foreign scope before dispatch.
- Query iteratively: start with the smallest query that can make progress, read the returned
  facts and completeness markers, then decide the next query from what came back.  Follow
  returned cursors and referenced IRIs.  There is no single-wave limit; a follow-up query
  driven by returned information is normal.  Do not guess facts you did not receive.
- Keep each query small: `limit` ≤ 10, `context_limit` ≤ 3, `depth` = 1; use the default
  `limit=10` for the initial direction query, then prefer several focused queries over one
  big pull, and page with `match_cursor`/`context_cursor` instead of raising the limit.  If a
  query returns irrelevant concept matches, rephrase with specific entity, relation, or
  property names.  The proxy defaults omitted fields to `depth=1`, `limit=10`,
  `context_limit=0`; set `context_limit=3` only when you deliberately need
  `related_context`.
- Exact navigation: once any returned item contains an absolute IRI, that IRI may be used
  directly as the next `query`.  The interface then enters exact-anchor mode and returns
  that node as the sole primary match with its direct neighborhood in `related_context`;
  use this instead of rephrasing keywords when you need a specific node's facts.
- Keep each query kind-focused with `resource_types`: `["instance"]` for entity lookup,
  `["relation", "fact"]` for relationship resolution, and `["fact"]` when reading a specific
  literal field/property value.  Query the entity name for an entity, and query the property
  name alone for a relationship or literal (for example `currentlyConsumesOutput`,
  `hasOutput`, `hasVersion`, `versionState`, or `fieldName`); the primary page then contains
  the asserted statements instead of just property definitions.  A fact-primary query
  returns asserted literals as primary matches with their `data.object` value; set
  `context_limit` to 0 when those primary facts already carry the needed literal.  This is
  usually smaller than paging through `related_context`, where shape constraints can appear
  alongside asserted facts.
- Batch independent queries: in each round you may issue several independent queries together
  in one inference; only queries that depend on an earlier answer must wait.  Prefer 2-3
  batched rounds over many single-query rounds.
- Converge and submit: iterate until the retrieved facts answer the question or an explicit
  unknown is warranted; you decide when the evidence is sufficient.  A typical complete
  answer needs no more than 2-3 batched rounds and no more than 10 successful proxy calls.
  Submit as soon as the facts answer the question; do not keep querying for its own sake or
  re-query the same fact with different wording.  If after the third round or the tenth
  successful proxy call the evidence is still incomplete, stop querying and submit an
  explicit incomplete result with a named gap or an unknown — more calls also make the
  required `evidence_refs` locator list longer and harder to bind correctly.
- The report is ONLY accepted through the `submit_examiner_report` tool call of the
  `examiner_report` MCP server; writing the report in your reply text is not a submission
  and will not be counted.
- Every successful proxy call yields exactly one `evidence_refs` locator.  Copy the returned
  `request_digest`, `response_digest`, and `artifact_path` exactly into that locator; never
  invent or rewrite those values.  The locator count must equal the successful-call count,
  in the exact order the calls succeeded; use `ref_id = "p<call_ordinal>"` (zero-based) so
  `p0, p1, ..., p<call_total-1>` is contiguous and complete.  There is no permitted reason to
  omit, merge, or drop a locator; a count mismatch is rejected with `receipt-count-mismatch`
  and cannot be repaired by a second submission.
- The `page` object describes only that one call's own pagination.  A complete response uses
  `{"ordinal": 0, "input_cursor": null, "output_cursor": null, "has_more": false,
  "sequence_complete": true}`; only the same call's own next page would use `ordinal: 1`.
  Never invent ordinal `1, 2, ...` across different tool calls (`page-sequence-invalid`).
- Preserve completeness markers and record explicit unknowns/gaps in the terminal report.  An
  incomplete retrieval cannot support a definitive conclusion; distinguish "not modeled" from
  "query missed it".
