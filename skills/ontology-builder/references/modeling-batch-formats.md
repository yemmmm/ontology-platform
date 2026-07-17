# Modeling Batch formats

Always read the current Modeling Context before constructing items. The runtime request schema and
returned supported commands are authoritative; this reference explains stable workflow rules, not a
second command registry.

## Batch envelope

One logical submission contains:

- `session_id`: active Project Build Session;
- stable `client_batch_id` and `idempotency_key`;
- one target `ontology_id`;
- `expected_workspace_version` from fresh Modeling Context;
- `mode`: `dry_run`, `apply_atomic`, or explicitly accepted `apply_partial`;
- `lease_token`: omitted for dry-run, required for apply;
- ordered `items` with stable `client_item_id`.

Retry the same logical submission with the same identity and payload. A deliberate revision gets new
client/idempotency values. Never mutate a previously submitted logical batch under its old key.

## Item content

Each item identifies a supported command and payload. Include:

- stable client item identity;
- rationale in domain language;
- competency-question references when relevant;
- Evidence Reference IDs or inline `document_name + excerpt` evidence actually used;
- item references/dependencies when one item consumes another item's created resource.

Do not supply Graph Set ID or graph IRI for ordinary Ontology modeling. Do not invent server resource
IDs before dry-run returns normalized identifiers.

## Modes and Findings

`dry_run` performs normalization and deterministic validation without applying mutations. Review all
Findings, including warnings and item dependency effects, before apply.

`apply_atomic` is the default write mode: any non-applicable item prevents the intended atomic group
from being partially accepted. `apply_partial` allows supported independent groups to succeed; use it
only after the user understands which items may remain unapplied and how the Agent will reconcile
them.

Conflict, stale workspace, invalid lease, active write fence, recovering attempt, or uncertain prior
outcome is a stop condition. Query the original batch/session and recover under the returned protocol.
