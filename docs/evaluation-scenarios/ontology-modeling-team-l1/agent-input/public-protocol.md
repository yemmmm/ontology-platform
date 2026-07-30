# Public L1 platform protocol

Only the separately launched Platform Protocol Agent receives this file, the approved candidate and a
run-local `protocol-scope.json` containing only the owned Project/Ontology IDs.
It must not alter the candidate's meaning. It may correct JSON, IRI, reference, required-field and
call-order mechanics.

1. Use `check_platform_health`, then `get_modeling_context(ontology_id)` to obtain the current
   workspace version. Create the Build Session with `create_build_session(project_id, client_session_id)`
   and no initial checkpoint (unless every required checkpoint field is known from the current schema)
   and acquire the supplied Ontology lease. Retain the session ID, its current revision, and lease token.
2. Convert the approved candidate into bounded generic Modeling Items. Each Item has a stable
   `client_item_id`, a current command-schema `command_kind`, `payload`, `depends_on`, source evidence,
   rationale, and competency-question IDs. Use only `create_class`, `create_property`,
   `create_relation_type`, `create_entity`, `create_relation` and `create_shape` when needed. A later
   Item must reference an earlier Item output only as
   `{ "item_ref": { "client_item_id": "...", "output": "resource_id" } }` or
   `{ "item_ref": { "client_item_id": "...", "output": "resource_iri" } }`; never use a
   `{client_item_id, field}` shorthand. Every reference must name that prior item in `depends_on`, and
   later Batches must use the stable output ID/IRI returned by the applied Batch, never an invented
   replacement. Do not change the candidate's
   business meaning, and do not manufacture an answer ontology beyond it.
   A Shape `path_id` is a `create_property` resource ID, not a relation-type ID. For object constraints,
   create a property with `object_class_id`; Shape constraints support only `path_id`, `min_count`,
   `max_count`, `datatype`, `pattern`, `enum_values`, and `description`. Do not use `class_iri` or
   unsupported `in` guidance.
3. Submit one immutable structural batch through `submit_modeling_batch`: keep its exact `items` and
   `client_batch_id` unchanged for a `mode="dry_run"` attempt followed by `mode="apply_atomic"`.
   Supply a fresh expected workspace version from the preceding platform response. The `dry_run` must
   omit `lease_token`; the `apply_atomic` attempt supplies the acquired lease token. Use a
   distinct idempotency key for each attempt. A `validated` dry run is required before apply. Obtain the
   authoritative immutable batch detail with `get_modeling_batch(batch_id)` after both attempts.
4. Submit a separate invalid/missing-version-classification candidate as `mode="dry_run"` only. It must
   receive `validation_failed`; never apply it. Read its immutable batch detail too.
5. Read the applied model with `get_ontology_read_model` (generic entity and fact/read-model surfaces),
   prove the synthetic Workflow has distinct Current Draft and Latest Version states, save a concise
   checkpoint with the current session revision, then complete the Build Session.
   Re-read the completed session to ensure the lease is released.

Do not invent business facts, use hidden materials, retry a semantic conflict, or put plaintext keys
in output files. Report a concise normalized result to `/work/protocol-result.json` with exactly:
`build_session_id`, `structural`, `negative_dry_run`, `workspace`, and `read_model`. `structural` has
`dry_run` and `apply`, each with `batch_id`, `client_batch_id`, `items_sha256`, and `attempt_status`;
those first three values must be identical across the transition. `negative_dry_run` has `batch_id`,
`attempt_status` equal to `validation_failed`, and `applied: false`. `workspace` has distinct `before` and `after` values.
`read_model` has `generic: true` and `draft_latest_distinct: true`. Do not include raw Items, keys,
queries, hidden material, or full receipts.
