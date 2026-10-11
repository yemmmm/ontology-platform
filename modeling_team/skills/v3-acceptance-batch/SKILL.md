---
name: v3-acceptance-batch
description: One-continuous-session R3.0-011 v3 acceptance batch rules for the Platform Examiner and the independent Acceptance judge over a single frozen hidden batch.
---

# v3 Acceptance Batch Session

This skill covers both R3.0-011 v3 batch sessions (Platform Examiner and
independent Acceptance judge). It is intentionally limited to the one frozen
batch packet and its frozen business references. Neither role controls another role's lifecycle or writes files. The original
owner can forward user flow messages; record_flow_confirmation acknowledges
only that role's actual pause/resume request and never submits a report. The Platform Examiner reads the
platform only through its authorized `platform_read_proxy` scope; the judge has
no platform access at all.

- Work the packet order. One question at a time, first to last. Each question
  needs exactly one ACCEPTED `submit_examiner_report` call; a rejected
  submission is corrected and resubmitted until it is accepted.
- The report counts only when `submit_examiner_report` is called on the
  `examiner_report` MCP server; reply text is not a submission.
- The role instruction mounted in this session defines the exact payload fields.
  Copy `schema_version` and `batch_id` from the packet; never invent identifiers.
- A rejection names the exact field to fix. Fix it and resubmit the same
  question; the batch sink accepts corrected reports for the whole session, so
  a rejection never justifies restarting or skipping the batch.
- The Platform Examiner may read only through the `platform_read_proxy` server,
  inside `authorized_scope`. The judge has no platform access at all.
- In reference packet v2, Judge uses `examiner_report.read_frozen_evidence` for
  relevant original material; this capability accepts run/batch/freeze/reference
  identities only, with no path, repository, database or production access.
  Reuse same frozen source/content digest/review version while it is in context;
  read other chapters or versions and reread when needed. Cite a relevant
  reference_id in every pass note; the Host validates actual source read receipts.
  Missing/failed original reads cannot pass. Inline v1 evidence remains readable
  under its original contract.
- If the first-turn runtime text supplies `frozen_material_ref`, the same
  frozen set is also enumerable through `list_handoff_material` and readable in
  `.txt` members named by the listed `reference_id`. Continue byte offsets until
  `read_complete`; list or partial pages alone do not create a source receipt.
  Once all pages of a member are covered, the Host preserves the original
  `read_frozen_evidence` receipt, so the report still cites the corresponding
  reference identity and digest.
- For a large complete verdict, the child may use the scoped report sink handoff tools, publish
  the UTF-8 verdict to the existing Host channel, and submit a one-field `report_ref`. Do not mix
  it with verdict fields. This reference never replaces `read_frozen_evidence` or its source-read
  receipt.
- Result-body registry transport retains complete platform response bodies once.
  Resolve each result_ref against result_body_registry; preserve each original
  question, response digest, locator, pagination and completeness. A reference or
  Consumer answer cannot replace actual response content.
- Neither role waits for a Source Examiner: this batch has none.


## Cooperative user waiting and task closure (R4.2-008 / R4.0-028)

When the original owner forwards a sourced pause, stop advancing the original
question/judging task, disclose in-flight work and the remaining question IDs,
and call the advertised record_flow_confirmation with exactly the original
request_id and action=pause. Then end the turn and wait on this original thread.
This waiting acknowledgement is not submit_examiner_report and cannot fill a
missing answer/verdict. The report sink and remaining task stay open while waiting.
Only an explicit resume message permits continuation: confirm action=resume,
then finish the remaining original questions without repeating accepted reports.
Use the same original scope, reports and evidence; waiting does not extend key or
authorization expiry, reset costs, or change the frozen packet.

The Consumer's genuine task closure seals the original report sink/report set;
its original thread may then serve read-only consults through the original owner
and still-valid scope. Consultation cannot resubmit/overwrite original reports.
If the task-closed owner requests a waiting acknowledgement, return the exact
flow_confirmation in the reply body as instructed because the old sink is closed.
The independent Judge is destroyed only at genuine task completion or necessary
failure cleanup; a confirmed waiting turn is neither completion nor failure.
Do not share Judge inputs, answers or reasons with Consumer/production/public chat.
