# Phase 4 Named-Graph Governance and Runtime State

> **Note (2026-07-08):** The evidence-storage portions of this design have
> been refactored. The `op:evidenceStatus` literal (including the
> `"missing_evidence"` marker shown below) and `prov:wasDerivedFrom`
> evidence edges have been removed; evidence now lives in the Postgres
> `fact_evidence_bindings` table. See
> `docs/superpowers/specs/2026-07-08-evidence-postgres-refactor-design.md`.
> The rest of this document remains accurate as Phase 4 architectural
> history.

## Status

Detailed design. Phase 4 builds on the Phase 1 runtime spine, Phase 2 semantic export baseline, and
Phase 3 governed direct semantic interfaces.

Phase 4 does not migrate all product reads and writes to RDF. It makes graph-native governance,
graph-set runtime state, derived-result staleness, and result-graph garbage collection explicit so
later migration phases can safely treat Oxigraph as the canonical semantic boundary.

## Goal

Make named graphs and graph sets the platform governance model.

The platform should no longer rely on draft/published graph promotion assumptions inside the
semantic refactor path. It should govern actual ontology/data graphs with per-graph editability,
track which graph sets belong to a working version, distinguish asserted/inferred/rule-derived
statements, and detect when derived outputs are stale.

## Confirmed Decisions

1. Actual ontology and data graphs are edited directly through governed semantic edits when their
   graph editability switch allows it.
2. Proposal graphs may exist for review-heavy workflows, but they are not the required write path.
3. OWL reasoning results are always written to `graph/reasoning-result/{run_id}` graphs.
4. Business rule results are always written to `graph/rule-result/{run_id}` graphs.
5. Source ontology/data graphs are never mutated by reasoning or business rule execution.
6. The current effective derived-result pointer is operational metadata in Postgres.
7. Superseded reasoning-result graphs are rebuildable derived data and may be garbage-collected
   after a newer successful run becomes current for the same graph set.
8. Phase 4 should choose a conservative statement-metadata representation that works with the
   selected Oxigraph version. Use RDF reification or named-graph metadata first if RDF-star / RDF
   1.2 quoted triple support is not complete enough for reliable storage and query.

## Non-Goals

- Do not implement full role-based access control or graph visibility policy.
- Do not migrate legacy product APIs to RDF-backed canonical writes; that belongs to later phases.
- Do not implement the full business rule engine; Phase 4 defines result graph boundaries and
  staleness metadata so Phase 5 can add execution.
- Do not require RDF-star / RDF 1.2 as a hard dependency until Oxigraph support is verified.
- Do not keep every historical derived graph forever by default.
- Do not make Neo4j a semantic source of truth.

## Vocabulary and Graph Categories

Phase 4 materializes the graph categories from the plan as platform-managed graph IRIs under
`Settings.semantic_graph_iri_prefix`.

With the default prefix:

```text
http://ontology-platform.local/semantic/graph/
```

the canonical graph IRI patterns are:

| Category | Pattern | Editable | Meaning |
| --- | --- | --- | --- |
| Ontology | `graph/ontology/{graph_id}` | yes | Asserted classes, properties, shapes-adjacent ontology terms, and schema axioms. |
| Data | `graph/data/{graph_id}` | yes | Asserted business entities, relations, fact claims, and evidence status. |
| Proposal | `graph/proposal/{proposal_id}` | optional | Candidate semantic edits for review workflows. |
| Evidence | `graph/evidence/{evidence_id}` | controlled | Evidence resources, source snippets, extraction provenance, and document attribution. |
| Policy | `graph/policy/{policy_id}` | controlled | Semantic policy metadata such as required review, masking, or obligations. |
| Import | `graph/import/{source_id}/{run_id}` | no after import | Raw imported source graph or normalized import output. |
| Validation run | `graph/validation-run/{run_id}` | no | SHACL report graph and validation-run provenance. |
| Reasoning run | `graph/reasoning-run/{run_id}` | no | OWL reasoner run metadata and provenance. |
| Reasoning result | `graph/reasoning-result/{run_id}` | no | OWL-inferred statements. |
| Rule run | `graph/rule-run/{run_id}` | no | Business rule execution metadata and provenance. |
| Rule result | `graph/rule-result/{run_id}` | no | Business-rule-derived statements. |
| Review | `graph/review/{review_id}` | controlled | Review decisions, comments, approvals, and rejected deltas. |

Only actual ontology/data graphs are ordinary direct-edit targets. Governance graphs may still be
written by platform workflows, but they should not be edited by the same open direct semantic edit
path unless the operation is explicitly allowed.

## Graph Registry

Phase 1 has `semantic_graph_states` for editability. Phase 4 extends that idea into a graph
registry while preserving the existing table's purpose.

Add `semantic_graph_registry`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `graph_iri` | text | Unique graph IRI. |
| `category` | string | `ontology`, `data`, `proposal`, `evidence`, `policy`, `import`, `validation_run`, `reasoning_run`, `reasoning_result`, `rule_run`, `rule_result`, or `review`. |
| `semantic_owner_type` | string nullable | `project`, `ontology`, `version`, `run`, `policy`, `evidence`, or `external_source`. |
| `semantic_owner_id` | string nullable | Owner id in the current product model or runtime metadata. |
| `mutable_by_direct_edit` | bool | True only for ordinary direct-edit targets such as actual ontology/data graphs. |
| `managed` | bool | True for platform-managed graph IRIs. |
| `created_by` | string nullable | Actor or service creating the graph record. |
| `created_at` / `updated_at` | timestamptz | Runtime bookkeeping. |
| `metadata` | JSONB | Category-specific options such as labels, source ids, shape versions, or engine versions. |

Keep `semantic_graph_states` for the actual editability switch:

- `semantic_graph_registry` answers "what kind of graph is this?"
- `semantic_graph_states` answers "may ordinary governed edits currently mutate it?"

Direct edits must check both:

```text
graph is platform-managed
  -> graph category allows direct edit
  -> graph editability state is editable
```

Unknown managed ontology/data graph IRIs may be auto-registered on first successful direct edit
during the transition. Unknown governance/result graph IRIs should require explicit platform
workflow creation.

## Working Version Graph Sets

Phase 4 represents a working version as a graph set. A graph set is the explicit list of source,
governance, evidence, policy, validation, reasoning, and rule graphs that define what a query,
validation run, projection, or product view should consider.

Add `semantic_graph_sets`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `name` | string | Human-readable name, for example `working-version:{version_id}`. |
| `scope_type` | string | `project`, `ontology`, `version`, `ad_hoc`, or `runtime`. |
| `scope_id` | string nullable | Product or runtime id for the graph set. |
| `status` | string | `active`, `superseded`, or `archived`. |
| `source_signature` | string | Deterministic hash of graph membership and source graph revisions. |
| `created_by` | string nullable | Actor or service. |
| `created_at` / `updated_at` | timestamptz | Runtime bookkeeping. |
| `metadata` | JSONB | Query defaults, labels, UI hints, or migration notes. |

Add `semantic_graph_set_members`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `graph_set_id` | string FK | Parent graph set. |
| `graph_iri` | text | Member graph IRI. |
| `role` | string | `asserted_ontology`, `asserted_data`, `evidence`, `policy`, `shape`, `validation_report`, `reasoning_result`, `rule_result`, `import`, or `review`. |
| `required` | bool | If false, absence should warn rather than fail. |
| `sort_order` | int | Stable display/query order. |
| `metadata` | JSONB | Membership-specific notes. |

The working-version graph set for an ontology version should usually include:

- one or more asserted ontology graphs,
- one or more asserted data graphs,
- generated or curated shape graphs,
- evidence graphs referenced by asserted data,
- policy graphs that apply to the version,
- the current effective reasoning-result graph when one exists,
- the current effective rule-result graph when one exists.

Graph set membership changes are governance events. They should update the graph-set
`source_signature` and mark dependent derived results stale.

## Source Graph Revisions

Staleness requires a cheap way to know whether an input graph changed. Phase 4 introduces source
graph revision metadata without storing RDF triples in Postgres.

Add `semantic_graph_revisions`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `graph_iri` | text | Source graph IRI. |
| `revision` | integer | Monotonic per graph. |
| `content_hash` | string nullable | Optional hash from exported graph content after successful mutation. |
| `last_edit_audit_id` | string nullable | Link to `semantic_edit_audits.id` when a direct edit changed the graph. |
| `changed_at` | timestamptz | Mutation time. |
| `changed_by` | string nullable | Actor or platform service. |
| `metadata` | JSONB | Change summary or hash method. |

On successful governed edits, increment the revision for each affected source graph. For large
graphs, content hashing may be deferred or computed asynchronously; the monotonic revision is the
minimum required signal.

Derived result runs record the graph revisions they consumed. If any consumed graph revision
changes, the derived result is stale.

## Derived Result Pointers

Phase 1 reasoning runs already store a result graph IRI. Phase 4 adds explicit current-effective
pointers for derived graphs.

Add `semantic_derived_result_pointers`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `graph_set_id` | string FK nullable | Graph set the result applies to. |
| `result_kind` | string | `reasoning` or `rule`. |
| `run_id` | string | Reasoning or rule run id. |
| `result_graph_iri` | text | Current effective result graph. |
| `source_signature` | string | Graph-set source signature consumed by the run. |
| `engine_name` | string nullable | Reasoner or rule engine. |
| `engine_version` | string nullable | Engine version or command signature. |
| `rule_version` | string nullable | For rule results. |
| `shape_version` | string nullable | For validation-sensitive results. |
| `status` | string | `current`, `stale`, `superseded`, or `failed`. |
| `became_current_at` | timestamptz nullable | Set after successful run promotion. |
| `metadata` | JSONB | Warnings, missing-evidence dependencies, and explanation pointers. |

A successful reasoning run with `persist_result_graph=true` may become current for its graph set
only after:

1. source graphs and graph-set membership are resolved,
2. the result graph is written,
3. run metadata is persisted,
4. the pointer is atomically updated to `current`,
5. previous current pointers for the same graph set and result kind become `superseded`.

Query layers that need inferred or rule-derived facts should read through the pointer rather than
guessing the latest run id.

## Statement-Level Metadata

Phase 4 must preserve statement metadata without depending on unsupported RDF features.

Decision path:

1. Verify the selected Oxigraph version's RDF-star / RDF 1.2 quoted triple support for parse,
   storage, SPARQL query, export, and update.
2. If support is complete enough, allow quoted triple metadata in governance graphs.
3. Otherwise use standard RDF reification or named statement resources.

The conservative default is named statement resources:

```turtle
@prefix op: <http://ontology-platform.local/semantic/vocab/> .
@prefix prov: <http://www.w3.org/ns/prov#> .

<http://ontology-platform.local/semantic/statement/{statement_id}>
  a op:StatementAnnotation ;
  rdf:subject <http://example.test/entity/alice> ;
  rdf:predicate <http://example.test/relation/enrolledIn> ;
  rdf:object <http://example.test/entity/course-1> ;
  op:assertionGraph <http://ontology-platform.local/semantic/graph/data/demo> ;
  op:assertionKind "asserted" ;
  op:evidenceStatus "missing_evidence" ;
  prov:wasGeneratedBy <http://ontology-platform.local/semantic/edit/{audit_id}> .
```

For inferred statements, use `op:assertionKind "owl_inferred"` and point to the reasoning run. For
rule-derived statements, use `op:assertionKind "rule_derived"` and point to the rule run.

The annotation graph should be a governance graph, not the source ontology/data graph. This keeps
source graphs focused on semantic assertions and keeps metadata queryable without mutating asserted
facts.

## Staleness Model

Derived outputs become stale when any dependency changes.

Reasoning result staleness triggers:

- any source ontology/data graph revision consumed by the reasoning run changes,
- graph-set membership changes,
- reasoner command, engine name, or engine version changes,
- reasoning task list changes,
- relevant shape/version context changes when the reasoning run used it,
- an input import graph is replaced by a newer import run.

Rule result staleness triggers:

- any source graph revision consumed by the rule run changes,
- graph-set membership changes,
- rule definition or rule version changes,
- rule engine version changes,
- upstream reasoning result pointer changes when rules depend on inferred facts,
- missing-evidence dependency state changes.

Validation report staleness triggers:

- data graph revision changes,
- shape graph revision changes,
- graph-set membership changes,
- SHACL engine options or inference mode change.

Staleness update strategy:

- Synchronous direct edit path marks known dependent derived pointers stale immediately after a
  successful mutation.
- A periodic or explicit reconciliation endpoint can recompute stale states from graph revisions
  and graph-set signatures.
- Stale derived graphs remain queryable only when the caller explicitly allows stale results or the
  read API labels them as stale.

## Garbage Collection

Phase 4 garbage collection applies only to rebuildable derived result graphs by default.

Reasoning-result GC rules:

1. Never delete a result graph referenced by a `current` pointer.
2. Do not delete a result graph from a failed run if it was never fully written.
3. A `superseded` reasoning-result graph is eligible after a configured retention window.
4. Keep run metadata, pointer history, and audit summaries even when deleting the RDF result graph.
5. Delete through the RDF store boundary with an explicit graph-drop operation.
6. Record GC status and errors in Postgres.

Add `semantic_graph_gc_runs`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `target_kind` | string | `reasoning_result`, later `rule_result`. |
| `status` | string | `running`, `succeeded`, or `failed`. |
| `candidate_count` | int | Graphs considered. |
| `deleted_count` | int | Graphs deleted. |
| `started_at` / `finished_at` | timestamptz | Run timing. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Deleted graph IRIs and retention settings. |

Rule-result GC should start more conservatively than reasoning GC because rule outputs may carry
business audit significance. Phase 4 may design it but should only enable reasoning-result GC by
default.

## API Surface

Phase 4 extends `/api/semantic/...` without changing the Phase 3 read/write separation.

`GET /api/semantic/graphs`

Returns registered graphs with category, editability, owner, revision, and derived-result status.

Query parameters:

```text
category=ontology|data|reasoning_result|rule_result|...
owner_type=ontology|version|run|...
owner_id=...
include_revisions=true|false
```

`POST /api/semantic/graphs`

Registers a platform-managed graph. Does not write triples by itself.

`GET /api/semantic/graph-sets/{graph_set_id}`

Returns graph-set metadata, members, source signature, and current derived result pointers.

`POST /api/semantic/graph-sets`

Creates or updates an explicit graph set. Updating membership recomputes the source signature and
marks dependent derived pointers stale.

`POST /api/semantic/graph-sets/{graph_set_id}/reasoning-runs`

Runs reasoning over a graph set instead of a loose list of source graph IRIs. This can wrap the
existing Phase 1 reasoning run service while adding pointer update and staleness metadata.

`POST /api/semantic/derived-results:reconcile`

Recomputes stale/current/superseded derived result state from graph-set signatures and graph
revisions.

`POST /api/semantic/derived-results:gc`

Runs garbage collection for eligible superseded reasoning-result graphs.

`GET /api/semantic/status`

Returns a governance summary:

- graph counts by category,
- locked/editable actual graph counts,
- stale reasoning/rule result counts,
- current effective result pointers,
- latest validation state where available.

## Service Design

Add or extend service boundaries:

```text
SemanticGraphRegistryService
  -> register graph
  -> classify graph category from IRI
  -> enforce direct-edit category policy
  -> return graph status summaries

SemanticGraphSetService
  -> create/update graph sets
  -> compute graph-set source signatures
  -> list member graphs by role

SemanticDerivedStateService
  -> update current result pointers
  -> mark dependent results stale
  -> reconcile stale state
  -> expose status summaries

SemanticGraphGcService
  -> find eligible superseded derived graphs
  -> delete result graphs through RdfStoreRepository
  -> persist GC run metadata
```

Extend `RdfStoreRepository` with:

```python
clear_graph(graph_iri: str) -> UpdateResult
graph_content_hash(graph_iri: str) -> str | None
```

`clear_graph` should issue a graph-scoped delete/drop that cannot affect other graphs. The service
must reject GC attempts for source ontology/data/evidence/policy graphs.

## Edit Flow Changes

Phase 3 edit flow remains the write boundary. Phase 4 adds registry, revision, and staleness side
effects:

```text
receive governed edit
  -> parse and compute affected graph IRIs
  -> require graph category allows direct edit
  -> require graph editability is true
  -> validate candidate state
  -> apply Oxigraph update
  -> write semantic_edit_audit
  -> increment affected graph revisions
  -> recompute graph-set signatures for graph sets containing affected graphs
  -> mark dependent validation/reasoning/rule pointers stale
```

These side effects should run in the same service operation as the edit audit from the caller's
perspective. If RDF mutation succeeds but metadata update fails, the service must return a clear
partial-failure state and reconcile by graph revision or audit id.

## Reasoning Run Changes

Phase 1 accepts `source_graph_iris`. Phase 4 adds graph-set-aware reasoning:

```text
resolve graph set
  -> collect asserted ontology/data graphs and required imports
  -> optionally include policy/shape context if configured
  -> execute OWL reasoner
  -> write graph/reasoning-result/{run_id}
  -> write graph/reasoning-run/{run_id} metadata graph if enabled
  -> persist run metadata
  -> set current effective reasoning pointer for graph set
  -> mark previous pointer superseded
```

The source graph set and result graph remain distinguishable in query output. Product projections
may merge them, but storage and metadata must preserve `asserted` vs `owl_inferred`.

## Rule Result Placeholder

Phase 4 prepares rule-result governance without implementing the full Phase 5 rule runtime.

Minimum Phase 4 support:

- graph category registration for `rule-run` and `rule-result`,
- derived result pointer kind `rule`,
- staleness rules for rule definitions and graph dependencies,
- status reporting that can show "no current rule result" or "rule result stale".

Rule execution APIs, DSL, SPARQL CONSTRUCT derivation, and explanation output belong to Phase 5.

## Query and Reporting Semantics

Storage must preserve graph boundaries. Query/reporting surfaces can offer merged views only when
they expose statement origin.

SPARQL query helpers should support these graph sets:

- asserted-only: ontology/data source graphs,
- asserted plus current reasoning: source graphs plus current reasoning-result graph,
- asserted plus current rules: source graphs plus current rule-result graph,
- full working view: source, current reasoning, current rule, evidence, and policy graphs.

Responses should include warnings when:

- a requested derived result is stale,
- no current derived result exists,
- a graph set includes missing optional graphs,
- a result includes missing-evidence assertions or derived statements depending on them.

## Test Strategy

Default backend tests should use fake RDF stores and in-memory/session fakes where practical.

Required tests:

- graph IRI classification returns the expected category for every canonical pattern,
- direct edits reject non-direct-edit graph categories,
- ontology and data graphs can be locked/unlocked independently,
- successful edits increment source graph revisions,
- graph-set source signatures change when membership or source revisions change,
- reasoning run over a graph set updates the current effective pointer,
- previous reasoning result pointer becomes superseded after a newer successful run,
- source graph edits mark dependent reasoning and rule pointers stale,
- GC does not delete current result graphs,
- GC deletes only eligible superseded reasoning-result graphs through the RDF store boundary,
- status reporting includes graph deltas, editability, validation state, and derived staleness.

Integration tests with a live Oxigraph service should cover graph deletion/export behavior, but the
default `cd backend && uv run pytest` suite should not require a live RDF service.

## Implementation Order

1. Add graph category classifier and graph registry models.
2. Add graph revision tracking and wire successful Phase 3 edits to revision increments.
3. Add graph-set models, membership APIs, and source-signature computation.
4. Add derived result pointer model and graph-set-aware reasoning pointer updates.
5. Add staleness reconciliation for source graph edits and graph-set membership changes.
6. Add governance status endpoint.
7. Add RDF store graph-clear operation and reasoning-result garbage collection.
8. Add rule-result placeholder metadata and status reporting, without implementing rule execution.
9. Add focused service/API tests and one optional Oxigraph integration test for graph clearing.

## Implementation Checklist

### 0. Documentation

- [x] State that Phase 4 is graph governance/runtime state, not full canonical product migration.
- [x] Separate Phase 4 graph-set/staleness design from Phase 5 rule and derivation execution.

### 1. Graph Registry

- [x] Add `SemanticGraphRegistryModel`.
- [x] Add migration for `semantic_graph_registry`.
- [x] Add graph IRI category classifier for every canonical graph pattern.
- [x] Auto-register managed ontology/data graphs on successful direct edit where safe.
- [x] Reject direct semantic edits to result/governance graphs unless a platform workflow allows
      them.

### 2. Source Revisions

- [x] Add `SemanticGraphRevisionModel`.
- [x] Increment graph revisions after successful governed edits.
- [x] Link revisions to `semantic_edit_audits.id` when available.
- [x] Add optional content hash support without requiring it for large graphs.

### 3. Graph Sets

- [x] Add `SemanticGraphSetModel`.
- [x] Add `SemanticGraphSetMemberModel`.
- [x] Add graph-set create/read/update service methods.
- [x] Compute deterministic source signatures from member graph IRIs, roles, and source revisions.
- [x] Mark dependent derived pointers stale when graph-set membership changes.

### 4. Derived Result Pointers

- [x] Add `SemanticDerivedResultPointerModel`.
- [x] Create/update current reasoning pointer after successful graph-set reasoning runs.
- [x] Mark previous pointer superseded after a newer run becomes current.
- [x] Add rule pointer placeholder support without implementing rule execution.
- [x] Include engine/version/source-signature fields in pointer metadata.

### 5. Staleness

- [x] Mark reasoning pointers stale when source graph revisions, graph-set membership, reasoner
      config, or task lists change.
- [x] Mark rule pointers stale when source graph revisions, graph-set membership, rule versions,
      rule engine versions, or upstream reasoning pointers change.
- [ ] Mark validation reports stale when data/shape graph revisions or validation options change.
- [x] Add explicit reconciliation service and endpoint.

### 6. Garbage Collection

- [x] Extend `RdfStoreRepository` with graph-scoped clear/drop support.
- [x] Add `SemanticGraphGcRunModel`.
- [x] Implement dry-run and execute modes for reasoning-result GC.
- [x] Refuse to delete source ontology/data/evidence/policy graphs through GC.
- [x] Preserve run metadata and pointer history after RDF result graph deletion.

### 7. API and MCP Surface

- [x] Add graph registry list/create endpoints.
- [x] Add graph-set read/create/update endpoints.
- [x] Add graph-set-aware reasoning run endpoint.
- [x] Add derived-result reconciliation endpoint.
- [x] Add derived-result GC endpoint.
- [x] Add semantic governance status endpoint.
- [x] Add MCP tools only for stable agent use cases: graph-set status, current derived pointers,
      and staleness checks.

### 8. Tests

- [x] Add service tests for graph classification, registry, revisions, graph sets, staleness, and
      GC candidate selection.
- [x] Add API tests for graph registry, graph-set status, reconciliation, and GC.
- [x] Update semantic edit tests to assert revision and staleness side effects.
- [x] Keep default backend tests independent of live Oxigraph.
- [x] Run `cd backend && uv run pytest`.

## Completion Criteria

- [ ] `cd backend && uv run alembic upgrade head`
- [ ] `cd backend && uv run pytest`
- [ ] Current effective reasoning pointers are maintained for graph-set reasoning runs.
- [ ] Locked ontology/data graphs remain independently editable or locked.
- [ ] Source, reasoning-result, and rule-result graph categories remain distinguishable in storage
      and status output.
- [ ] Superseded reasoning-result graphs can be garbage-collected without changing current query
      behavior.
- [ ] Governance status reporting shows graph deltas, editability, validation state, and derived
      result staleness.
