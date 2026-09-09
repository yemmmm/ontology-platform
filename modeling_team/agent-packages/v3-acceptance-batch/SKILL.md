---
name: v3-acceptance-batch
description: One-continuous-session R3.0-011 v3 acceptance batch rules for the Platform Examiner and the independent Acceptance judge over a single frozen hidden batch.
---

# v3 Acceptance Batch Session

This skill covers both R3.0-011 v3 batch sessions (Platform Examiner and
independent Acceptance judge). It is intentionally limited to the one frozen
batch packet in the first turn. No collaboration, lifecycle control, or
filesystem writes are available to either role. The Platform Examiner reads the
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
- Neither role waits for a Source Examiner: this batch has none.
