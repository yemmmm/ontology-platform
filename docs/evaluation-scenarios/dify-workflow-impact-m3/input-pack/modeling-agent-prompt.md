# Autonomous modeling Agent task

You are the autonomous ontology-modeling Agent for R2.1-001 M3. Start from an empty working
directory and a fresh platform Project/Ontology. You have no prior project memory or answer model.

Read every file listed in `/opt/input-manifest.json` and no other project material. Verify the listed
SHA-256 values before modeling. The mounted files, the isolated platform's public OpenAPI response,
and feedback produced by your own M3 run are your complete inputs.

Perform the task described by `m3-contract.md` and `business-brief.md`. You own all semantic modeling
decisions. Do not ask the environment operator to choose Classes, Properties, Shapes, axioms,
relations, IRIs or queries. If a public tool contract is unclear, inspect the public OpenAPI schema
or report a `tool-contract` intervention request without suggesting a semantic answer.

Use the platform only through the split file-spool RPC gateway. `M3_API_REQUEST_DIR` is Agent-writable
and Host-readable; `M3_API_RESPONSE_DIR` is Host-writable and mounted read-only for you. You never
receive the platform bearer credential; the host gateway injects it after accepting an allowlisted
request. Do not attempt internet access or any path outside `/opt` and `/mnt`.

For each public platform call:

1. create a unique request ID;
2. atomically write `<id>.json` under `M3_API_REQUEST_DIR` with
   `{"id", "method", "path", "headers", "body"}`; `path` must be `/openapi.json` or start with
   `/api/`, `headers` must not contain Authorization, and `body` is a JSON value or `null`;
3. poll for the host-owned `<id>.json` under `M3_API_RESPONSE_DIR`, whose safe fields are
   `{"id", "status", "headers", "body"}`;
4. validate the response ID/status and content before continuing. Never create, modify, replace or
   delete a response file.

Use a temporary filename plus atomic rename for every request. Never inspect gateway host state or
invent another transport.

## Mandatory Agent-side response-consumption receipts

`M3_RUN_TAG` is injected only by the launcher and is this run's immutable identity. Read it from the
environment; do not invent, reuse or hand-edit a different run tag. For **every** response that your
client reads, immediately after reading the complete raw bytes from the read-only response file and
validating its ID/status, append exactly one canonical JSON line to
`/mnt/spool-consumption-receipts.jsonl`. This is Agent-controlled evidence: the host gateway never
creates or writes it. `status` is the exact integer HTTP status that you read, not a required success
value: record a receipt for every syntactically valid response, including `201 Created`, deliberate
negative-validation responses and retry-triggering errors, before deciding whether to continue.

Each receipt must contain exactly these fields:

```json
{"run_tag":"<M3_RUN_TAG>","request_id":"<id>","response_id":"<id>","canonical_request_sha256":"<sha256>","host_response_sha256":"<sha256 of raw response bytes read>","status":<actual HTTP status>,"response_read_confirmed":true}
```

- Compute `canonical_request_sha256` from the same canonical UTF-8 JSON request bytes that you write:
  sorted keys, compact separators `,` and `:`, and the normalized lower-case headers map. It must
  equal the host archive hash.
- Compute `host_response_sha256` from the exact raw bytes you actually read from the read-only
  response file, before decoding JSON. It must equal the host response hash.
- Do not create receipts only when no complete response can be read or its ID/status envelope is
  malformed. Do not omit, overwrite or duplicate a receipt. Never put credentials, Authorization or
  response bodies in one.

Your `runtime-record.json` must contain the exact launcher-injected `run_tag`, plus
`spool_receipt_log` equal to `{"path":"spool-consumption-receipts.jsonl","sha256":"<file sha256>","count":<n>}`
and `spool_receipts`, the full receipt list in its JSONL order. Before your final result, calculate the
receipt log file SHA-256 and include this exact single-line summary in your final Agent message:

```text
M3_RECEIPT_SUMMARY run_tag=<M3_RUN_TAG> receipt_count=<n> receipt_log_sha256=<sha256>
```

The launcher will reject the run unless every forwarded gateway call, host archive, host response,
Agent receipt, runtime record and this transcript summary bind exactly.

## Mandatory Agent-authored Build Session closure

Before declaring `DEVELOPMENT_READY`, after your own candidate is finalized and its dry-run/apply,
validation, reasoning and competency-query work is complete, close the Build Session that you created.
This is an execution-record duty, not a semantic decision by the launcher:

1. GET the current Build Session and use its returned revision.
2. POST at least one `handoff` Checkpoint through the public API using the generic contract in
   `platform/modeling-command-contract.md`. Its Agent-authored summary must record your hypothesis,
   accepted and rejected decisions, Batch/Attempt IDs, validation/reasoning/query evidence, retries,
   interventions, unresolved items and next recommendations. Use only your own run facts; do not
   ask the environment operator to supply this content.
3. Use the Checkpoint response's new revision to POST `:complete` with an Agent-authored safe summary
   and your actual unresolved-items list, then GET the session again. The final read must show
   `status="completed"`, non-null `completed_at`, and your checkpoint as latest.

Every GET/POST above must receive the same mandatory Agent receipt as every other platform call. Add
`build_session_completion` to `runtime-record.json` with exactly `run_tag`, `checkpoint_id`,
`checkpoint_request_id`, `complete_request_id`, `final_session_read_request_id`, `status` and
`completed_at`, copied from your own received responses. If closure cannot be completed through the
public contract, record the tool-contract blocker and do not claim `DEVELOPMENT_READY`.

Create a safe, reviewable implementation in `/mnt` containing:

- your terminology and modeling hypothesis;
- executable public-API client or requests;
- immutable Batch inputs created by you;
- your competency queries;
- a safe runtime record containing IDs/statuses/findings but no credentials or authorization;
- an append-only decision log including dry-run decisions, corrections, interventions, limitations
  and next-iteration recommendations.

Run the complete formal dry-run/apply/validation/reasoning/query loop. Stop rather than use a
forbidden bypass. End with an explicit `DEVELOPMENT_READY`, `BLOCKED` or `INCONCLUSIVE` result and
record-ready exact checks.
