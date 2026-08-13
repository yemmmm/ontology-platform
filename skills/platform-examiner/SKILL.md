---
name: platform-examiner
description: Read-only, ticket-scoped retrieval of modeled resources and Producer-created validation/reasoning results.
---

# Platform Examiner

This Skill is a generic retrieval contract, not a business answer key.  The Runner supplies
the question, Project/Ontology/graph scope, model-state envelope, and the frozen MCP allowlist.

- Use only the ticket-bound read shim and the declared read tools.  Never use a write,
  validation-start, reasoning-start, key, Project, Ontology, or Lease operation.
- Bind every request and response to the exact ticket Project, Ontology, graph set, and
  model-state digest.  Reject an omitted or foreign scope before dispatch.
- Use one minimum-sufficient retrieval wave: in the first inference, select only the read-only
  proxy requests needed for the current question and issue them as one parallel assistant
  tool-call wave. The wave may produce no more than 6 successful proxy calls; use each allowed
  tool at most once. Every successful call must yield exactly one evidence_refs locator, so
  the locator count equals the current-child proxy receipt count. Do not serialize independent
  exploration, probe one read before deciding on another, retry, or re-read. After the wave
  returns, the next inference must submit the typed terminal report; do not start another
  retrieval wave, follow a cursor, or widen the completeness/receipt gate. If six calls cannot
  cover the needed facts, preserve the resulting unknown and report an explicit incomplete
  result with an explicit gap.
- Mandatory locator count check before submission: mechanically count the successful proxy
  calls in the returned wave and compare with the `evidence_refs` array about to be sent. The
  number of `evidence_refs` items must be exactly equal to the number of successful proxy
  calls; there is no permitted reason to omit, merge, or drop a locator. Every successful call
  that returned a receipt must appear as its own locator with its exact `request_digest`,
  `response_digest`, and `artifact_path`. A report whose locator count differs from the
  successful-call count is automatically rejected by the Host with `receipt-count-mismatch`
  and cannot be repaired by a second wave or a follow-up message. Re-count immediately before
  sending; when the counts differ, add the missing locators in the same report and send it in
  that same inference.
- Mandatory ordinal alignment: each successful proxy response carries `call_ordinal`
  (zero-based) and `call_total` (running successful-call count). Align `evidence_refs`
  one-to-one in the exact order the calls succeeded; the locator at position `i` must come
  from the response whose `call_ordinal` is `i`, and the number of locators must equal the
  `call_total` of the last successful response. Use `ref_id = "p<call_ordinal>"` so the Host
  can verify the ordinal sequence `p0, p1, ..., p<call_total-1>` is contiguous and complete.
  Before submitting, list the received ordinals, confirm none is missing, then send the
  report in the same inference.
- No locator selection by importance: you never decide which successful calls deserve a
  locator. Every single successful call that returned a receipt gets exactly one locator,
  unconditionally: if two calls answered the same fact, both locators stay; if a call
  returned an empty or unusable response, its locator stays and the unknown/gap is recorded
  for that fact; if a call appears redundant, it still gets its locator. The locator set is
  a mechanical inventory of the wave, not a judgment about which reads matter. Before
  sending, recount: for every ordinal `0 .. call_total-1`, confirm the locator
  `p<ordinal>` exists in `evidence_refs`. A report with fewer locators than successful
  calls is rejected with `receipt-count-mismatch` and cannot be fixed by a second wave or a
  follow-up message.
- Page field is per-call, not a wave-wide sequence: the `page` object in a locator
  describes only that one call's own pagination, never a sequence across different calls.
  Each distinct successful call has its own locator whose `page.ordinal` starts at `0`. A
  complete response uses `{"ordinal": 0, "input_cursor": null, "output_cursor": null,
  "has_more": false, "sequence_complete": true}`. Only when the same call itself returns
  `has_more: true` with a cursor would that same call's next page use `ordinal: 1` and
  carry the returned cursor; the frozen allowlist never permits a second page read in this
  wave, so every locator in this report has `page.ordinal = 0` and `has_more = false`.
  Never invent ordinal `1, 2, ...` across different tool calls: a report whose locator
  pages form an invented sequence is rejected with `page-sequence-invalid`.
- Keep query basis, Evidence, lineage, response digests, and explicit completeness in the
  terminal report. If a first-wave response is cursor-bearing, truncated, incomplete, ambiguous,
  or missing a fact, preserve its completeness markers and state the unknown and explicit gap
  in that same report. A dependent follow-up read is a gap to report, not another retrieval
  inference, and incomplete retrieval cannot support a definitive conclusion.
  For every successful proxy call, copy the proxy-returned `request_digest`,
  `response_digest`, and `artifact_path` exactly into its `platform_read` evidence ref;
  never invent or normalize those values.
- Distinguish “the platform has not modeled this fact” from “the current query missed it”.
  An incomplete/truncated query cannot support a definitive conclusion.
- Read existing Producer-created validation/reasoning results through the generic read
  wrappers only; never start or rerun those processes.
- Do not read approved source files, prior Examiner dialogue, hidden expected answers, or
  prior verdicts.  Report an explicit unknown when the modeled facts do not answer the question.
