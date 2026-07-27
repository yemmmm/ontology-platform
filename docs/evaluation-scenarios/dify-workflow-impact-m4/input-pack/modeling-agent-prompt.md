# Autonomous M4 modeling Agent task

Start from an empty workspace and a fresh platform Project, Ontology and Build Session. Read every
file listed in `/opt/input-manifest.json`; verify the listed hashes. Those files, the isolated
platform public OpenAPI response, platform feedback produced by this run, and one response to each
of your own eligible clarification requests are your complete inputs.

Own the ontology design. Never ask the host to select RDF structure, Classes, Properties, Shapes,
axioms, IRIs, Batch items, or queries. Ask a business clarification only when a missing visible-input
fact changes the modeled boundary, current target, relationship semantics, or consumer conclusion.
Do not ask about facts already stated in the brief.

Before the principal schema Batch, obtain one eligible response for each of the three consequential
ambiguities explicitly stated in the visible brief: invocation lifecycle, output-contract identity, and
missing-score handling. A `not_eligible` response leaves that ambiguity unresolved: revise the question
without combining decisions, or atomically record `BLOCKED` and stop. Do not begin modeling while any
listed ambiguity remains unresolved.

## Clarification spool

`M4_CLARIFICATION_REQUEST_DIR` is writable by you. `M4_CLARIFICATION_RESPONSE_DIR` is host-owned and
read-only. For one material uncertainty at a time, atomically create `<id>.json` in the request
directory using canonical UTF-8 JSON (sorted keys and compact separators) with exactly:

```json
{"affected_terms":["<your term>"],"business_impact":"<why the model or consumer changes>","id":"<unique id>","question":"<plain business question>"}
```

`id` must match `[a-z][a-z0-9_-]{0,63}` (one to 64 characters). `affected_terms` contains one to six non-empty strings.
The question and impact are your words; do not encode an ontology recipe. Wait for the matching
read-only response before sending another request. Never
create, overwrite, delete, rename, or inspect a response file other than your matching response.

A response is canonical JSON with the same `id` and one of:

- `{"answer":"...","id":"...","status":"answered"}`
- `{"id":"...","reason":"...","status":"uncertain"}`
- `{"id":"...","reason":"...","status":"not_eligible"}`

Validate its raw SHA-256 and envelope. For each response consumed, append a canonical line to
`clarification-consumption-receipts.jsonl` with `run_tag`, `request_id`, `response_id`,
`response_sha256`, `status`, and `response_read_confirmed: true`. Bind it in your decision log to
the changed assumption and either an immutable Batch rationale or a named explicit-gap item.

## Platform spool, budget, and final state

Use `M4_API_REQUEST_DIR` and `M4_API_RESPONSE_DIR` for the generic API spool. Requests use the
existing public envelope `{id, method, path, headers, body}`; do not send Authorization. Follow the
generic field-level command contract at `/opt/platform/modeling-command-contract.md`; it supplies
the public request shapes, revision/lease rules, receipt schema, and required order. Do not spend
time guessing opaque payload fields or inventing a domain recipe.

## Resource ID integrity

Immediately atomically persist every returned Project, Ontology, and Build Session ID in
`runtime-record.json.resource_ids.project_id`, `.ontology_id`, and `.build_session_id`, respectively.
For **every** Project-, Ontology-, or Build Session-scoped API path, just before publishing its
request envelope, read the corresponding ID just-in-time from that persisted runtime record; do not
reuse an earlier response, a remembered value, or a stale shell variable. This includes child-resource
creation, ontology context, lease, Modeling Batch, Build Session GET, checkpoint, complete, and final
GET paths.

If you use a Bash helper, put its scratch ID and path variables inside a function and declare every
such scratch variable `local`; do not export, source, or retain them as global state. Before an atomic
spool publish, assert that every Project, Ontology, or Build Session ID embedded in the path equals the
matching persisted runtime-record ID. If any assertion fails, rebuild the request locally from the
runtime record or atomically record `BLOCKED`; never forward a mismatched path.

Treat the completion-first order as a closed time budget. The single principal Shape-containing schema
Batch is first dry-run once and then applied unchanged once. Its successful apply is immediately followed
by invalid-instance dry-run, one valid-instance dry-run, that same valid-instance apply, validation,
reasoning, one governed query, Build Session GET, checkpoint, complete, and final GET. Once the
principal apply succeeds, do not submit another schema Batch, explore payloads, use an operation/Rule
Definition/Rule Run endpoint, or issue a second producer query. Its core ends at 600 seconds; seconds
600–660 are only for complete, final GET, runtime persistence and final audit. If any closed-sequence operation fails, atomically record
`BLOCKED` and stop rather than retrying or probing.

For the first valid-instance candidate, apply it unchanged when its dry-run validates. A single
correction Batch is permitted only after a 2xx dry-run `validation_failed` response whose every
blocking finding is SHACL and attributes non-empty fingerprints and client item IDs. Keep all
unaffected items byte-for-byte unchanged; modify only attributed items without changing their IDs,
command kinds, or dependencies. Bind the original/correction batch and response hashes, fingerprints,
item hashes and per-item reasons in the runtime record and decision log. A correction must validate,
then apply unchanged immediately; any other failure is `BLOCKED`, with no third candidate or later
semantic operation.

For that one correction, set `runtime-record.json.instance_correction` to exactly this object shape
(replace every placeholder; SHA-256 values are lower-case hexadecimal):

```json
{"changed_items":[{"after_sha256":"<correction item hash>","before_sha256":"<original item hash>","client_item_id":"<changed existing item id>","reason_finding_fingerprint":"<blocking finding fingerprint naming this item>"}],"correction_batch_id":"<new batch id>","correction_dry_run_request_id":"<request id>","correction_dry_run_request_sha256":"<canonical request sha256>","correction_dry_run_response_sha256":"<response sha256>","original_batch_id":"<failed candidate batch id>","original_finding_fingerprints":["<every blocking finding fingerprint, sorted>"],"original_request_id":"<request id>","original_request_sha256":"<canonical request sha256>","original_response_sha256":"<response sha256>"}
```

Append exactly one matching canonical decision-log line:
`{"event":"instance_correction","evidence":<the exact instance_correction object>}`. The host
will compare it with its request summaries and protected responses. Do not add the correction record
when the first candidate validates.

For `before_sha256` and `after_sha256`, hash the full respective Modeling Batch item object, not only
its payload: SHA-256 of its canonical UTF-8 JSON encoded with sorted keys and compact separators. This
is exactly the gateway `canonical_item_sha256` value.

`original_batch_id` and `correction_batch_id` are the request `client_batch_id` values, not server batch IDs.

The one governed query must preserve—not suppress—the exact optional-rule-absent warning permitted by
the contract. Record its code, message, request ID and response SHA-256 in `optional_rule_absent`; do
not create or run a rule to remove it. Immediately after **each** API response atomically update
`/mnt/runtime-record.json` and append canonical lines to
`api-consumption-receipts.jsonl` and `decision-log.jsonl`. Record API metadata/hashes, not
credentials or raw response bodies.

Before a known timeout, unrecoverable API failure, lease conflict, or other block, atomically set
`runtime-record.json` to `terminal_status: "BLOCKED"` or `"INCONCLUSIVE"`, include a concise reason,
and append the matching decision-log line. End only with `DEVELOPMENT_READY`, `BLOCKED`, or
`INCONCLUSIVE`. Set `DEVELOPMENT_READY` only after the runtime record contains all required success
and rejection receipts, a matching checkpoint, and actual final-GET evidence that the Build Session
is completed. A missing, malformed, ineligible, or unverified clarification response is not a
confirmed business fact.
