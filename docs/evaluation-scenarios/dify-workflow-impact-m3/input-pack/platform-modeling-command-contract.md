# Generic Modeling Batch command contract

## Purpose and authority

This document exposes the generic structured command contract already enforced by the current platform. It
describes transport and payload semantics only; it does not prescribe an ontology, resource names, IRIs,
Shapes or queries for the M3 business scenario.

The contract is derived from:

- `backend/app/api/schemas.py` — `ModelingBatchSubmit` and `ModelingItemInput`;
- `backend/app/services/modeling_handlers.py` — allowed command kinds, fields, outputs and `item_ref`;
- `backend/app/services/semantic_command_compiler.py` — required fields and nested payload behavior.

The public OpenAPI currently renders `ModelingItemInput.payload` as a generic JSON object, so this companion
contract supplies the deterministic field details that OpenAPI cannot express.

## Batch envelope

Submit one immutable batch to:

```text
POST /api/build-sessions/{session_id}/modeling-batches
```

The JSON body is:

```json
{
  "client_batch_id": "unique-within-session",
  "ontology_id": "ontology UUID",
  "idempotency_key": "unique-within-session",
  "mode": "dry_run | apply_atomic | apply_partial",
  "expected_workspace_version": "current modeling-context workspace version",
  "lease_token": "required for apply, omitted for dry_run",
  "items": [
    {
      "client_item_id": "unique-within-batch",
      "command_kind": "one supported command",
      "payload": {},
      "depends_on": [],
      "evidence_reference_ids": [],
      "evidence": [],
      "rationale": "Agent modeling reason",
      "competency_question_ids": []
    }
  ]
}
```

Use a new immutable `client_batch_id` and idempotency key after changing content. To apply an unchanged
validated candidate, keep the same `client_batch_id` and Items, reacquire the current workspace version and
lease, change mode to `apply_atomic`, and use a new idempotency key. This creates a new Attempt for the same
immutable Batch content.

## References inside a Batch

Create commands expose:

```json
{
  "resource_id": "platform resource ID",
  "resource_iri": "platform resource IRI"
}
```

Within the same Batch, any nested payload value can reference a prior create Item:

```json
{
  "item_ref": {
    "client_item_id": "the-create-item",
    "output": "resource_id"
  }
}
```

or use `"output": "resource_iri"`. Add the referenced Item to `depends_on`; the platform also derives the
implicit dependency. `item_ref` is Batch-local. In a later Batch, use the stable `resource_id` or
`resource_iri` returned by the applied Batch; never reuse an old `item_ref`.

A wrapper exactly shaped as `{"resource_id": "value"}` resolves to the scalar value. It does not mark an
entity property value as an IRI. Object links between entities must use `create_relation`.

## Build Session checkpoint and completion contract

These routes record the external Agent's own progress. They do not prescribe any ontology concept,
IRI, model decision or query result.

1. Read the current session before a checkpoint:

```text
GET /api/build-sessions/{session_id}
```

Use `body.session.revision` as `expected_revision`. To append a final Agent-authored checkpoint:

```json
POST /api/build-sessions/{session_id}/checkpoints
{
  "client_checkpoint_id": "new unique client ID",
  "expected_revision": 1,
  "phase": "handoff",
  "current_step": "Agent-authored final execution step",
  "next_step": "complete build session",
  "ontology_id": "the current Ontology ID",
  "summary": "Agent-authored safe summary of hypothesis, accepted/rejected decisions, Batch/Attempt, validation, reasoning, query, retry, intervention, unresolved and recommendation facts",
  "blockers": [],
  "related_batch_id": "a Batch ID from this run when applicable"
}
```

The response contains `body.session.revision` and `body.checkpoint.id`. Use that returned revision,
not a guessed value, to complete:

```json
POST /api/build-sessions/{session_id}:complete
{
  "client_request_id": "new unique client ID",
  "expected_revision": 2,
  "summary": "Agent-authored safe completion summary",
  "unresolved_items": []
}
```

The completion response is the session summary with `status="completed"` and non-null
`completed_at`. GET the session again and retain the final response, whose `latest_checkpoint.id`
must equal the checkpoint you just created. Every call uses the ordinary spool request/response receipt
contract; a non-2xx but well-formed response is still receipted before the Agent decides its next step.

## Commands needed for generic ontology structure and fixtures

Only fields listed below are accepted. `ontology_id`, graph IDs/IRIs, shape graph IRIs and actor are forbidden
inside Item payloads because the Batch and workspace determine those targets.

### `create_class`

Required:

- `name`: string.

Optional:

- `class_id`: stable client-selected ID; otherwise the platform assigns one;
- `description`: string;
- `aliases`: string array;
- `parent_class_ids`: array of Class resource IDs;
- `external_mappings`: object.

`parent_class_ids` creates `rdfs:subClassOf` axioms and can therefore provide a supported RDFS inference
expectation.

### `create_property`

Required:

- `class_id`: domain Class resource ID;
- `name`: string;
- one of:
  - `datatype`: `xsd:*` name or full datatype IRI for a DatatypeProperty;
  - `object_class_id`: range Class resource ID for an ObjectProperty.

Optional:

- `property_id`: stable ID;
- `description`: string.

The emitted IRI is a `/property/{id}` IRI. A Shape `path_id` resolves to this same Property IRI. If an object
relationship must be constrained by a Shape, define it with `create_property(object_class_id=...)` and use
that emitted Property IRI in `create_relation`.

### `create_relation_type`

Required:

- `name`;
- `source_class_id`;
- `target_class_id`.

Optional:

- `relation_type_id`, `description`, `symmetric`, `transitive`, `scope_policy`, `status`.

This emits a `/relation-type/{id}` ObjectProperty. The current structured Shape compiler does not use
relation-type IDs for `path_id`; use `create_property` for Shape-constrained predicates.

### `create_shape`

Required:

- `target_class_id`: target Class resource ID.

Optional:

- `shape_id`: stable ID;
- `constraints`: array. Each constraint requires `path_id`, the resource ID of a `create_property`.

Supported constraint fields:

```json
{
  "path_id": "property resource ID",
  "min_count": 0,
  "max_count": 1,
  "datatype": "xsd:string",
  "pattern": "regular expression",
  "description": "constraint explanation",
  "enum_values": ["allowed literal values"]
}
```

Only include fields needed by the constraint. A Shape and entities may be submitted together if dependencies
and references are resolvable; later Batches may reference already applied stable IDs.

### `create_entity`

Required:

- `class_iri_or_legacy_id`: a full Class IRI or a Class resource ID;
- `label`: string.

Optional:

- `entity_id`: stable ID;
- `aliases`: string array;
- `properties`: object mapping full predicate IRI to literal JSON scalar.

Every `properties` value is compiled as an RDF literal. Do not put entity IRI references in `properties`;
create those object edges with `create_relation`.

### `create_relation`

Required scalar IRIs:

- `source_entity_iri`;
- `relation_type_iri`: any applied OWL ObjectProperty IRI, including a Property IRI emitted by
  `create_property(object_class_id=...)`;
- `target_entity_iri`.

All three fields must be scalar IRI strings after any same-Batch `item_ref` resolution.

### `update_fact` and `delete_fact`

`update_fact` requires:

- `subject_iri`, `predicate_iri`;
- `old_object_value`, `new_object_value`;
- optional `old_object_is_iri`, `new_object_is_iri` booleans.

`delete_fact` requires:

- `subject_iri`, `predicate_iri`, `object_value`;
- optional `object_is_iri`.

These operate on the Ontology's governed data graph. Do not supply a graph target override in a Modeling
Item.

## Create/update/delete identity rule

Create commands may receive a stable client ID or let the platform assign one. Update/delete commands require
the relevant stable resource ID or full IRI. Read the applied Batch outputs or current read models rather than
guessing a platform IRI.

## Evidence and rationale

- `evidence_reference_ids` point only to direct official or synthetic source excerpts.
- Agent modeling choices, hypotheses and reasons belong in Item `rationale`, Build Checkpoints and the
  execution log, not in Evidence.
- A Modeling Item without Evidence is allowed but is explicitly reported as having no Evidence.

## Failure handling

- `invalid_command_payload`: required, nested or type semantics are wrong;
- `unresolved_item_ref`: Batch-local reference is unknown, forward-invalid or uses an unsupported output;
- `shacl_violation`: candidate violates active or candidate Shapes;
- `workspace_revision_conflict`: refresh modeling context and build a new immutable Batch;
- `lease_*`: reacquire/renew the lease before apply.

Never weaken validation or switch write paths after a finding. Record the Batch, Attempt, finding, decision and
new corrective Batch.
