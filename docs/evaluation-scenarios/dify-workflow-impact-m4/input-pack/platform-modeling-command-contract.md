# Generic public modeling command contract

Use only `/openapi.json` and public `/api/` requests through the M4 API file spool. This is a
field-level transport contract, not an ontology recipe: choose all names, IRIs, resource contents,
Shape constraints, evidence, and queries from the visible business brief and your own modeling
judgement. Do not request a host-supplied ontology or domain answer.

## Common transport and receipts

Every request is canonical JSON in the existing spool envelope:

```json
{"body":{},"headers":{"content-type":"application/json"},"id":"unique-request-id","method":"POST","path":"/api/..."}
```

Use a new request ID for every call. Immediately after every response, atomically replace
`/mnt/runtime-record.json`, append one canonical JSON line to `/mnt/api-consumption-receipts.jsonl`,
and append the corresponding decision/evidence line to `/mnt/decision-log.jsonl`. Do not retain
credentials or raw response bodies in either log. A receipt records at least `request_id`, actual
`status`, `canonical_request_sha256`, `raw_response_sha256`, and the semantic result fields below.

`runtime-record.json` must always be valid JSON and include `run_tag`, `terminal_status`, `receipts`,
`checkpoint`, and `build_session_completion`. Its terminal status is exactly
`DEVELOPMENT_READY`, `BLOCKED`, or `INCONCLUSIVE`. Before a known block, an invalid response, or a
self-detected timeout, atomically record that terminal status and reason, then append its decision
log line. The host may still terminate a process that exceeds its deadline.

## Resource ID integrity for every scoped request

Immediately atomically persist every returned Project, Ontology, and Build Session ID in
`runtime-record.json.resource_ids.project_id`, `.ontology_id`, and `.build_session_id`, respectively.
For **every** Project-, Ontology-, or Build Session-scoped API path, just before publishing its
request envelope, read the corresponding ID just-in-time from that persisted runtime record; do not
reuse an earlier response, a remembered value, or a stale shell variable. This applies to child-resource
creation, ontology context, lease, Modeling Batch, Build Session GET, checkpoint, complete, and final
GET paths.

If you use a Bash helper, put its scratch ID and path variables inside a function and declare every
such scratch variable `local`; do not export, source, or retain them as global state. Before an atomic
spool publish, assert that every Project, Ontology, or Build Session ID embedded in the path equals the
matching persisted runtime-record ID. If any assertion fails, rebuild the request locally from the
runtime record or atomically record `BLOCKED`; never forward a mismatched path.

## Establish a fresh modeling workspace

1. Create the Project with `POST /api/projects` and body
   `{"name":"...","description":"..."}`. Keep its returned `id`.
2. Create an Ontology with `POST /api/projects/{project_id}/ontologies` and body
   `{"name":"...","description":"...","external_mappings":{}}`. Retain its returned ontology ID.
3. Create a Build Session with
   `POST /api/projects/{project_id}/build-sessions`. Its body includes at least a unique
   `client_session_id`; include any required title/summary fields from OpenAPI. Retain session ID and
   returned session revision.
4. Read `GET /api/ontologies/{ontology_id}/modeling-context` and use its
   `workspace.workspace_version` string, not guesses, for the Batch version. Read
   `GET /api/ontologies/{ontology_id}/workspace-context` for the `default_graph_set_id` and members
   when a graph-set semantic operation needs them.

   Workspace member `role` values returned by the platform are authoritative. For the current public
   workspace, the exact required roles are `asserted_ontology`, `asserted_data`, `shapes`, and `policy`;
   do not locally abbreviate, rename, translate, or infer any role. A fresh workspace reported ready may
   proceed to the first Modeling Batch even when its initial hashes are empty and every resource count is
   zero. Block only when a required member is actually absent or the workspace is reported non-ready.
5. Acquire the ontology lease using
   `POST /api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire` with
   `{"client_request_id":"...","expected_session_revision":<current revision>,"rotate_token":false}`.
   Retain the lease token and lease/session revisions. For every state-changing call, use the latest
   returned expected revision; renew the lease through its public renew operation when necessary.

## Immutable Modeling Batch envelope

Submit `POST /api/build-sessions/{session_id}/modeling-batches` with this generic shape:

```json
{
  "client_batch_id":"stable-batch-id",
  "ontology_id":"ontology-id",
  "idempotency_key":"unique-key-per-attempt",
  "mode":"dry_run",
  "expected_workspace_version":"workspace-version",
  "lease_token":"required-for-apply-only",
  "items":[{
    "client_item_id":"stable-item-id",
    "command_kind":"create_class",
    "payload":{},
    "depends_on":[],
    "evidence_reference_ids":[],
    "evidence":[],
    "rationale":"visible-source rationale",
    "competency_question_ids":[]
  }]
}
```

`mode` is one of `dry_run`, `apply_atomic`, or `apply_partial`; use only `dry_run` and
`apply_atomic` here. Omit `lease_token` for a dry-run; an apply repeats the unchanged validated
`client_batch_id` and `items`, supplies the current workspace version and `lease_token`, changes
`mode` to `apply_atomic`, and uses a new
idempotency key. Do not apply a changed candidate without a new dry-run. Use `depends_on` plus
`{"item_ref":{"client_item_id":"...","output":"resource_id"}}` or `resource_iri` where a
later command needs an earlier generated value.

The relevant public `ModelingItem` command payloads have these minimum fields:

| Command | Required generic payload fields | Useful optional fields |
| --- | --- | --- |
| `create_class` | `name` | `class_id`, `description`, `aliases`, `parent_class_ids`, `external_mappings` |
| `create_property` | `class_id`, `name`, exactly one of `datatype` or `object_class_id` | `property_id`, `description` |
| `create_relation_type` | `name`, `source_class_id`, `target_class_id` | `relation_type_id`, `description`, `symmetric`, `transitive`, `scope_policy`, `status` |
| `create_shape` | `target_class_id`, `constraints` | `shape_id` |
| `create_entity` | `class_iri_or_legacy_id`, `label` | `entity_id`, `aliases`, `properties` |
| `create_relation` | `source_entity_iri`, `relation_type_iri`, `target_entity_iri` | none |

Each Shape constraint includes `path_id` and may include `min_count`, `max_count`, `datatype`,
`pattern`, `description`, or `enum_values`. Object-property/relation values are scalar resource IRIs, not
embedded object structures.

## Completion-first required order

This is a closed, budgeted action plan. The principal schema Batch is the anchor: it must contain every
generic schema resource needed for the visible brief and at least one Shape; dry-run it once and then
apply that unchanged candidate once. When that principal Shape-containing apply succeeds, schema is frozen: do not submit
another Batch containing `create_class`, `create_property`, `create_relation_type`, or `create_shape`.
The very next platform call after that apply must be the independent invalid-instance dry-run below.
Do not call an operation endpoint, Rule Definition endpoint, or Rule Run endpoint. Do not explore,
probe, or retry. A failure in the closed sequence below is `BLOCKED`, with its receipt and reason
recorded before stopping.

Execute exactly this full order. The first ten actions must finish within the
first 600 seconds; only complete, final GET, runtime persistence, and final-audit convergence may use
seconds 600–660.

1. **Principal schema dry-run**: dry-run the sole Shape-containing schema Batch. Record
   `receipts.principal_schema_dry_run`; it must return `mode: "dry_run"` and
   `attempt_status: "validated"`.
2. **Shape apply**: atomically apply exactly the unchanged principal Batch. Record
   `receipts.shape_apply`; it must return `mode: "apply_atomic"`, `attempt_status: "applied"`, and
   `batch_status: "applied"`.
3. **Independent invalid-instance dry-run**: submit a separate `dry_run` instance batch that
   deliberately violates one of your applied Shape constraints. The public Batch response must be
   HTTP 2xx with `attempt_status: "validation_failed"` and a blocking finding whose code is
   `"shacl_violation"`; never apply that Batch. Record `receipts.invalid_shape_dry_run` with its
   request ID, 2xx status, response hash, and attempt ID.
4. **Valid instance dry-run**: submit one resource/relation dry-run. If it is validated, atomically
   apply that exact Batch. If, and only if, the 2xx dry-run response is `validation_failed`, never
   applied, and every blocking finding is `shacl_violation` with a non-empty `finding_fingerprint`
   and non-empty `client_item_ids`, submit one new correction Batch; otherwise record `BLOCKED`.
   Bind the original request/response hashes, attempt and batch, every fingerprint, correction batch,
   before/after item hashes, and each changed item plus its reason fingerprint in both runtime record
   and decision log. The correction uses a new batch ID and idempotency key; it may change only found
   item IDs, retaining their IDs, command kinds and dependency topology. It must dry-run validated and
   then immediately apply its exact unchanged Batch; a correction failure is `BLOCKED` with no third try.
   The required `runtime-record.json.instance_correction` and canonical `decision-log.jsonl` line have
   the exact shape in `modeling-agent-prompt.md`; record every blocking fingerprint sorted and one
   `{client_item_id,before_sha256,after_sha256,reason_finding_fingerprint}` entry for every changed
   item. The host derives unchanged item equality, item-ID set, command kind and dependency topology
   from protected gateway summaries, so a no-op correction or a changed non-finding item is rejected.
5. **Valid instance apply**: atomically apply the validated first or correction Batch once and record
   `receipts.valid_instance_apply` only when its response has `mode: "apply_atomic"`,
   `attempt_status: "applied"`, and `batch_status: "applied"`. Preserve its attempt ID.

Every invalid or valid instance Batch has a non-empty `command_kinds` list containing only the
generic instance commands `create_entity` and `create_relation`; it contains none of
`create_class`, `create_property`, `create_relation_type`, or `create_shape`. The gateway audits this
safe command-kind summary so the final host gate can enforce the schema freeze.
6. **Validation**: call `POST /api/semantic/validation-runs` with concrete
   `{"data_graph_iris":["..."],"shape_graph_iris":["..."],"inference":"..."}`. Record
   `receipts.validation` only when its result says `conforms: true`; include `conforms: true` in
   that receipt.
7. **Reasoning**: call
   `POST /api/semantic/graph-sets/{default_graph_set_id}/reasoning-runs` with
   `{"tasks":["consistency"],"persist_result_graph":true,"engine_version":"...","shape_version":"..."}`.
   Record `receipts.reasoning` only when the actual response has `status: "succeeded"`,
   `consistent: true`, and a `derived_pointer` with `status: "current"`; persistence and this
   current pointer are required for this milestone.
8. **Governed positive query**: call the public scoped semantic query operation exactly once (for example
   `POST /api/semantic/sparql:query`) with `project_id`, `scope_mode`, `ontology_ids`, a query chosen
   by you, and optional `timeout_seconds`/`result_limit`. It must return a positive result,
   `truncated: false`, `scope.status: "complete"`, no excluded Ontologies, and exactly the requested
   single Ontology. Its scope's reasoning derived state must be `current` for the preceding reasoning
   run, while its rule derived state must be `missing`. The only allowed warning is exactly
   `{"code":"derived_result_missing","message":"No current rule result pointer."}`. Record its code,
   message, request ID and response SHA-256 as the explicit `optional_rule_absent` decision; do not
   create or run a rule to remove that warning.
9. **Pre-checkpoint GET, checkpoint, complete, final GET**: first `GET` the Build Session to obtain its real current
   revision. Create a handoff checkpoint with
   `POST /api/build-sessions/{session_id}/checkpoints` body
   `{"client_checkpoint_id":"...","expected_revision":<GET revision>,"phase":"handoff","current_step":"...","next_step":"...","ontology_id":"...","summary":"...","blockers":[],"related_batch_id":"..."}`.
   Store the returned checkpoint ID and revision. Complete with
   `POST /api/build-sessions/{session_id}:complete` body
   `{"client_request_id":"...","expected_revision":<checkpoint returned revision>,"summary":"...","unresolved_items":[]}`.
   Then actually `GET /api/build-sessions/{session_id}` and record `receipts.final_get`; only call
   the run ready if that response shows `status: "completed"`, `completed_at`, and the same
   `latest_checkpoint_id`.

Before setting `DEVELOPMENT_READY`, the runtime record must contain successful
`principal_schema_dry_run`, `shape_apply`, `valid_instance_dry_run`, `valid_instance_apply`,
`validation`, `reasoning`, `governed_query`, `pre_checkpoint_get`, `checkpoint`, `complete`, and
`final_get` receipts, the rejected `invalid_shape_dry_run` receipt, `checkpoint.id`, and a
`build_session_completion` object
linking the matching `latest_checkpoint_id`, complete request ID, final-GET request ID, completion
status, and `completed_at`. If any required receipt is missing, do not claim readiness.
