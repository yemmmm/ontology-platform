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
- Follow every pagination cursor and record the complete page chain.  Keep query basis,
  Evidence, lineage, response digests, and explicit completeness in the terminal report.
  For every successful proxy call, copy the proxy-returned `request_digest`,
  `response_digest`, and `artifact_path` exactly into its `platform_read` evidence ref;
  never invent or normalize those values.
- Distinguish “the platform has not modeled this fact” from “the current query missed it”.
  An incomplete/truncated query cannot support a definitive conclusion.
- Read existing Producer-created validation/reasoning results through the generic read
  wrappers only; never start or rerun those processes.
- Do not read approved source files, prior Examiner dialogue, hidden expected answers, or
  prior verdicts.  Report an explicit unknown when the modeled facts do not answer the question.
