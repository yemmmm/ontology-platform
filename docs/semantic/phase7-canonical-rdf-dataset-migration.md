# Phase 7 Canonical RDF Dataset Migration

## Status

Detailed design. Phase 7 builds on the Phase 1 semantic runtime spine, the Phase 2 namespace and
mapping baseline, the Phase 3 governed direct semantic edit path, the Phase 4 graph registry and
graph-set runtime state, the Phase 5 reasoning/validation/derivation services, and the Phase 6
graph-derived product API and projection layer.

Phase 7 is the source-of-truth transition. It should not start until graph-derived read parity,
governed semantic writes, validation, reasoning, projection rebuild, and rollback procedures are
proven in representative environments.

## Goal

Move canonical semantic state from the current custom Postgres/Neo4j-backed model into Oxigraph RDF
Dataset storage.

After Phase 7, asserted ontology structure, asserted business facts, evidence semantics,
provenance, semantic catalog mappings, identifier-resolution semantics, validation reports,
reasoning results, rule results, graph governance metadata, and statement annotations are stored as
named graphs in Oxigraph. Structured product APIs and direct semantic APIs both write through the
same governed RDF representation. Postgres remains for operational workloads, while Neo4j, search,
vector stores, frontend caches, and compact JSON views are rebuildable projections.

## Confirmed Decisions

1. Oxigraph RDF Dataset becomes the canonical semantic store after migration gates pass.
2. Phase 2 namespace and IRI mapping are the migration contract for current product objects.
3. Structured product APIs compile user actions into governed RDF graph deltas instead of writing
   independent semantic state into legacy tables.
4. Direct semantic APIs and structured product APIs share the same validation, editability,
   audit, graph revision, staleness, and projection invalidation pipeline.
5. Postgres keeps operational records where relational storage is the right workload: users,
   sessions, credentials, jobs, connector settings, service settings, run metadata, migration run
   metadata, graph registry state, graph-set membership, current result pointers, and non-semantic
   product records.
6. Neo4j, search, vector stores, and frontend read caches are projections rebuilt from Oxigraph
   graph sets and current derived-result pointers.
7. Legacy semantic write paths stay enabled during shadow and dual-write stages. They are disabled
   only after parity, rollback, rerun, validation, reasoning, edit, and projection rebuild behavior
   are proven.
8. The migration must be idempotent. A failed or interrupted migration run can be safely rerun for
   the same scope without duplicating semantic statements or corrupting graph revisions.
9. Rollback must restore the platform to the previous canonical write path until old semantic
   writes are permanently removed.

## Non-Goals

- Do not remove Postgres from the system.
- Do not store RDF triples, quads, ontology axioms, fact semantics, evidence semantics, or
  statement annotations in Postgres as a second source of truth.
- Do not make Neo4j, search, vector indexes, or frontend caches authoritative.
- Do not change the Phase 2 IRI contract during migration except through an explicit compatibility
  version and parity plan.
- Do not migrate secrets, connector credentials, user sessions, job queues, or other operational
  records into RDF.
- Do not disable legacy semantic writes until the deprecation criteria in this document are met.
- Do not require ordinary frontend users to author RDF syntax. Product APIs remain
  business-friendly wrappers over canonical RDF writes.

## Migration Architecture

Phase 7 adds a migration orchestrator and a canonical write router around the existing semantic
services.

```text
Legacy semantic stores
  Postgres product tables
  Neo4j semantic/traversal state
  catalog and connector records
  validation/reasoning/rule operational state
        |
        v
SemanticMigrationService
  -> Phase 2 mapping/export adapters
  -> graph inventory and batch planner
  -> RDF diff/import writer
  -> parity checker
  -> projection rebuild coordinator
  -> migration run metadata repository
        |
        v
Oxigraph RDF Dataset
  graph/ontology/{graph_id}
  graph/data/{graph_id}
  graph/shapes/{graph_id}
  graph/evidence/{evidence_id or project_id}
  graph/policy/{policy_id}
  graph/import/{source_id}/{run_id}
  graph/validation-run/{run_id}
  graph/reasoning-run/{run_id}
  graph/reasoning-result/{run_id}
  graph/rule-run/{run_id}
  graph/rule-result/{run_id}
  graph/review/{review_id}
```

The migration should run scope-by-scope rather than as one global transaction. A scope is normally
an ontology version, project, catalog source, connector source, or import source. Each scope gets a
migration run record, batch records, a deterministic graph inventory, and parity reports.

The canonical cutover is controlled by feature flags or settings:

| Setting | Purpose |
| --- | --- |
| `SEMANTIC_CANONICAL_STORE` | `legacy`, `shadow_rdf`, `dual_write`, or `rdf`. |
| `SEMANTIC_PRODUCT_WRITE_MODE` | `legacy_only`, `legacy_primary_rdf_shadow`, `dual_write_compare`, or `rdf_primary`. |
| `SEMANTIC_READ_MODE` | `legacy`, `rdf_shadow_compare`, or `rdf`. |
| `SEMANTIC_LEGACY_WRITE_BLOCKED` | Blocks old semantic write handlers after deprecation gates pass. |
| `SEMANTIC_MIGRATION_BATCH_SIZE` | Default object count per batch. |
| `SEMANTIC_MIGRATION_PARITY_REQUIRED` | Prevents cutover when parity checks fail. |

## Migration Inventory

The migration inventory is a deterministic manifest of every semantic object and projection input
that must be represented in RDF before cutover.

### Schema and Ontology Inventory

| Source | Canonical graph | Mapping |
| --- | --- | --- |
| Ontology records and versions | `graph/ontology/{ontology_id}` or version-scoped ontology graph | `owl:Ontology`, version IRI, graph-set membership. |
| Classes | `graph/ontology/{ontology_id}` | `owl:Class`, `rdfs:label`, `rdfs:comment`, `skos:altLabel`, hierarchy. |
| Properties | `graph/ontology/{ontology_id}` | `owl:DatatypeProperty` or `owl:ObjectProperty`, domain/range, datatype, cardinality hints. |
| Relation types | `graph/ontology/{ontology_id}` | Object properties with scope, source/target constraints, status, symmetric/transitive flags. |
| Controlled values | `graph/ontology/{ontology_id}` | `skos:Concept` and vocabulary membership. |
| External mappings | `graph/ontology/{ontology_id}` | `owl:sameAs`, close/exact match predicates, source attribution. |
| Generated SHACL shapes | `graph/shapes/{ontology_id}` | Phase 2 generated shapes plus shape version metadata. |

### Data and Evidence Inventory

| Source | Canonical graph | Mapping |
| --- | --- | --- |
| Entities | `graph/data/{ontology_id or version_id}` | `op:Entity`, class typing, labels, aliases, property values. |
| Relations | `graph/data/{ontology_id or version_id}` | Direct object-property triples plus `op:Relation` resources for ids/status. |
| Fact claims | `graph/data/{ontology_id or version_id}` | `op:FactClaim`, predicate/value, confidence, audit status, stale state. |
| Evidence links | `graph/data/...` and `graph/evidence/{project_id}` | `prov:wasDerivedFrom`, `op:evidenceStatus`, evidence resource links. |
| Missing-evidence facts | `graph/data/...` | Explicit `op:evidenceStatus "missing_evidence"` and warning metadata. |
| Extraction provenance | `graph/evidence/{project_id}` | PROV-O activity, agent, skill/model version, source document/chunk. |
| Review decisions | `graph/review/{review_id}` | Approval/rejection, reviewer, comments, accepted graph delta. |

### Governance and Runtime Inventory

| Source | Canonical or operational target | Mapping |
| --- | --- | --- |
| Graph registry records | Postgres operational plus optional RDF metadata graph | Category, owner, mutability, managed flag. |
| Graph editability | Postgres operational | Per-actual-graph lock state used by write checks. |
| Graph sets | Postgres operational | Working-version graph memberships and source signatures. |
| Graph revisions | Postgres operational | Revision and hash metadata for source graph changes. |
| Validation runs | Postgres summary plus `graph/validation-run/{run_id}` | SHACL report, engine/version, graph set and shape version. |
| Reasoning runs | Postgres summary plus `graph/reasoning-run/{run_id}` | Reasoner metadata, source signature, tasks, warnings. |
| Reasoning results | `graph/reasoning-result/{run_id}` | OWL-inferred statements only. |
| Rule runs | Postgres summary plus `graph/rule-run/{run_id}` | Rule/version, dependencies, explanations. |
| Rule results | `graph/rule-result/{run_id}` | Business-rule-derived statements only. |
| Derived-result pointers | Postgres operational | Current/stale/superseded pointers for read/projection selection. |

### Catalog, Connector, and Identifier Inventory

Catalog and connector semantics are migrated when they affect semantic meaning or identifier
resolution. Credentials and connection secrets stay in Postgres.

| Source | Canonical or operational target | Mapping |
| --- | --- | --- |
| Catalog entries | `graph/data/{project_id}` or catalog graph | Dataset/source resource, labels, ownership, semantic type. |
| Semantic mappings | `graph/ontology/{ontology_id}` or `graph/import/{source_id}/{run_id}` | Source field to class/property/relation mapping statements. |
| Connector definitions | Postgres operational plus RDF source metadata | Connector type, source IRI, non-secret metadata. |
| Connector credentials | Postgres operational | Not represented in RDF. |
| Identifier rules | `graph/policy/{policy_id}` or ontology graph | Canonical id patterns, aliases, same-as policy, resolution precedence. |
| Identifier resolution results | `graph/data/...` or review graph | `owl:sameAs` or platform match predicates with provenance and confidence. |

## Batch and Run Metadata

Migration runs are operational state. They belong in Postgres because they coordinate retries,
locking, deployment gates, and parity reports.

Add `semantic_migration_runs`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key and migration run id. |
| `scope_type` | string | `project`, `ontology`, `version`, `catalog_source`, `connector_source`, `global`, or `ad_hoc`. |
| `scope_id` | string nullable | Product scope id. |
| `mode` | string | `dry_run`, `shadow`, `dual_write_backfill`, `cutover`, or `rollback`. |
| `status` | string | `pending`, `running`, `succeeded`, `failed`, `rolled_back`, or `superseded`. |
| `phase2_mapping_version` | string | Mapping/context version used for this run. |
| `source_snapshot_signature` | string | Deterministic signature of source object ids and updated timestamps. |
| `target_graph_set_id` | string nullable | Graph set produced or updated. |
| `started_at` / `finished_at` | timestamptz | Run timing. |
| `created_by` | string nullable | Actor or deployment process. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Settings, batch size, counts, warnings, and rollback pointers. |

Add `semantic_migration_batches`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `migration_run_id` | string FK | Parent run. |
| `batch_index` | int | Stable order within the run. |
| `object_kind` | string | `class`, `property`, `entity`, `relation`, `fact_claim`, `evidence`, `catalog_mapping`, etc. |
| `source_ids` | JSONB array | Source ids included in the batch. |
| `target_graph_iris` | JSONB array | Graphs touched by the batch. |
| `status` | string | `pending`, `running`, `succeeded`, `failed`, or `skipped`. |
| `inserted_quad_count` | int | Number of quads inserted. |
| `deleted_quad_count` | int | Number of quads removed during replacement. |
| `source_hash` | string | Deterministic hash of source records. |
| `target_hash` | string nullable | Hash of generated RDF payload. |
| `started_at` / `finished_at` | timestamptz | Batch timing. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Warnings, graph deltas, and idempotency keys. |

Add `semantic_migration_parity_reports`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `migration_run_id` | string FK | Parent run. |
| `check_name` | string | Stable parity check id. |
| `scope_type` / `scope_id` | string | Scope checked. |
| `status` | string | `passed`, `failed`, `warned`, or `skipped`. |
| `legacy_count` | int nullable | Count from old model. |
| `rdf_count` | int nullable | Count from RDF-derived projection. |
| `diff_summary` | JSONB | Missing, extra, and changed item summaries. |
| `sample_diffs` | JSONB | Bounded examples for investigation. |
| `created_at` | timestamptz | Report time. |
| `metadata` | JSONB | Query versions, tolerances, and warnings. |

## Graph Mapping and Phase 2 Use

Phase 7 must reuse the Phase 2 mapping rather than inventing new IRIs.

The migration adapter flow is:

```text
load source records
  -> compute stable Phase 2 IRIs and graph IRIs
  -> build RDF dataset fragment
  -> normalize blank nodes where possible
  -> compute deterministic target hash
  -> validate generated RDF parseability
  -> compare with existing target graph fragment
  -> apply idempotent graph delta through governed RDF writer
```

Rules:

1. Every migrated resource uses the same stable IRI pattern exposed by Phase 2 exports.
2. Existing source ids remain traceable through RDF properties such as `op:sourceSystemId` or
   migration metadata.
3. Blank nodes are avoided for migrated product resources. Use stable IRIs for classes, properties,
   entities, relations, fact claims, evidence, rules, and mappings.
4. SHACL shapes are generated with a shape version. Validation parity references that version.
5. Graph-set membership is created or updated after graphs are loaded, not before.
6. Graph revisions are incremented only after a batch successfully commits to Oxigraph.
7. Legacy tables are not mutated by the migration except for operational migration metadata and
   optional read-mode/cutover settings.

## Migration Flow

### 1. Preflight

Preflight does not write RDF.

Checks:

- Oxigraph is reachable and reports healthy.
- Phase 2 namespace manifest is available and versioned.
- Target graph IRIs do not conflict with unmanaged graphs.
- Source object inventory is complete for the selected scope.
- Required Phase 4 graph registry and graph set tables exist.
- Phase 5 validation/reasoning services are available or explicitly disabled for dry runs.
- Phase 6 RDF-derived projections exist for the parity surface being migrated.
- Current legacy semantic writes can be frozen per scope during cutover.
- Rollback mode and retention window are configured.

### 2. Dry Run

Dry run creates a migration run and batch plan, generates RDF payload hashes, and runs parse and
shape checks against generated artifacts without writing target source graphs.

Expected outputs:

- inventory counts by object kind,
- graph inventory,
- batch plan,
- generated RDF byte/hash summaries,
- parse and SHACL failures,
- unsupported source records,
- estimated projection rebuild impact.

### 3. Shadow Backfill

Shadow backfill writes RDF graphs while legacy remains canonical.

Flow:

```text
freeze batch source snapshot
  -> generate RDF for batch
  -> write to target named graph through migration writer
  -> update graph revision and migration batch status
  -> run scoped parity checks
  -> rebuild shadow projections
  -> keep product reads and writes on legacy path
```

Shadow writes should not affect user-visible behavior except for explicit shadow comparison
reports.

### 4. Dual-Write Compare

Dual-write compare keeps legacy writes primary but routes the same product change through the RDF
writer in shadow mode.

For every supported product write:

```text
receive product command
  -> execute legacy write
  -> compile command to RDF graph delta
  -> validate and apply RDF delta
  -> compare legacy-derived projection with RDF-derived projection for affected scope
  -> record mismatch without changing canonical read path
```

If the RDF write fails after the legacy write succeeds, the write response may still follow legacy
behavior during this stage, but the mismatch must block cutover for that scope.

### 5. RDF Primary Cutover

RDF primary cutover changes the source of truth for migrated scopes.

Cutover sequence:

1. Put the target scope into a short semantic write freeze.
2. Drain in-flight legacy semantic write jobs for the scope.
3. Run final incremental backfill from the last source snapshot.
4. Run mandatory parity checks.
5. Run SHACL validation over the target graph set.
6. Run required reasoning/rule refreshes or mark their pointers stale with explicit status.
7. Rebuild Neo4j/search/vector/frontend projections from RDF.
8. Switch product read mode to RDF for the scope.
9. Switch product write mode to RDF primary for the scope.
10. Unfreeze semantic writes.
11. Keep legacy semantic tables read-only for rollback until the retention window expires.

### 6. Legacy Write Deprecation

Legacy semantic writes are disabled only after the deprecation criteria are met. The old tables may
remain as historical snapshots or operational references until a later removal phase.

## Service and Repository Changes

### `SemanticMigrationService`

Responsibilities:

- Build migration inventory and batch plans.
- Call Phase 2 mapping/export adapters.
- Generate deterministic RDF dataset fragments.
- Validate generated RDF syntax and SHACL constraints before writing.
- Apply idempotent graph deltas to Oxigraph.
- Maintain migration run, batch, and parity metadata.
- Coordinate graph registry, graph revisions, graph sets, and derived-result staleness.
- Trigger projection rebuilds and parity checks.
- Execute rollback or rerun procedures.

### `CanonicalSemanticWriteService`

This service becomes the shared write path for direct semantic edits and structured product
commands after cutover.

Flow:

```text
receive direct edit or product command
  -> compile to semantic graph delta
  -> resolve target graph set and graph categories
  -> check graph editability and managed graph policy
  -> run SHACL/platform validation
  -> create edit audit metadata
  -> apply RDF update to Oxigraph
  -> increment graph revisions
  -> mark derived results and projections stale
  -> return compact business response or semantic edit response
```

Product command compilers should be thin adapters. They translate business operations such as
class creation, relation creation, assertion submission, catalog mapping update, or identifier
resolution acceptance into the same graph delta contract used by direct semantic edits.

### Repository Boundaries

`RdfStoreRepository` must support migration-safe operations:

```python
put_named_graph(graph_iri: str, content: str, format: RdfFormat) -> GraphWriteResult
replace_named_graph_if_hash_matches(
    graph_iri: str,
    content: str,
    format: RdfFormat,
    expected_previous_hash: str | None,
) -> GraphWriteResult
apply_dataset_delta(delta: RdfGraphDelta) -> GraphWriteResult
export_named_graph(graph_iri: str, format: RdfFormat) -> str
drop_named_graph(graph_iri: str) -> GraphDropResult
graph_content_hash(graph_iri: str) -> str
```

Legacy repositories remain available for:

- migration source reads,
- rollback during the retention window,
- non-semantic operational records,
- parity comparison until old semantic writes are deprecated.

They must not keep accepting semantic writes after `SEMANTIC_LEGACY_WRITE_BLOCKED=true`.

## API Changes

Phase 7 should expose administrative migration APIs under `/api/semantic/migrations/...`. These
APIs are operational controls, not ordinary modeling surfaces.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/semantic/migrations:preflight` | Check scope readiness and produce inventory summary. |
| `POST /api/semantic/migrations` | Create a dry-run, shadow, dual-write, cutover, or rollback run. |
| `GET /api/semantic/migrations/{run_id}` | Return run status, counts, warnings, and linked reports. |
| `POST /api/semantic/migrations/{run_id}:run-next-batch` | Execute the next pending batch for controlled deployments. |
| `POST /api/semantic/migrations/{run_id}:rerun-failed-batches` | Recompute and rerun failed or skipped batches. |
| `POST /api/semantic/migrations/{run_id}:parity-check` | Run or rerun parity checks for the scope. |
| `POST /api/semantic/migrations/{run_id}:cutover` | Execute guarded RDF-primary cutover for a completed migration. |
| `POST /api/semantic/migrations/{run_id}:rollback` | Restore legacy-primary mode for the scope. |

Product APIs keep their business-shaped contracts. Internally, migrated scopes route writes to
`CanonicalSemanticWriteService` and reads to RDF-derived projections. Unmigrated scopes continue to
use legacy behavior until their cutover.

Direct semantic APIs remain under `/api/semantic/...` and already target RDF. In Phase 7 they no
longer represent a sidecar path for migrated scopes; they write the same canonical representation
as structured product APIs.

## Write-Path Changes

### Before Cutover

```text
Product API write
  -> legacy service/repository
  -> Postgres/Neo4j semantic state
  -> optional RDF shadow write and compare

Direct semantic edit
  -> governed semantic edit service
  -> Oxigraph sidecar/candidate graph state
```

### After Cutover

```text
Product API write
  -> product command compiler
  -> CanonicalSemanticWriteService
  -> Oxigraph source graph
  -> graph revision/staleness/projection updates

Direct semantic edit
  -> CanonicalSemanticWriteService
  -> Oxigraph source graph
  -> graph revision/staleness/projection updates
```

Rules:

1. Product APIs must not bypass RDF governance for migrated semantic objects.
2. Direct semantic edits must not bypass product-level platform checks where those checks protect
   required invariants.
3. Both paths must produce comparable audit metadata and graph deltas.
4. Both paths must enforce graph editability before mutation.
5. Both paths must use the same missing-evidence semantics.
6. Both paths must mark validation, reasoning, rule, Neo4j, search, vector, and frontend
   projections stale when their source graph set changes.

## Read and Projection Changes

Phase 6 read models become the ordinary product read path for migrated scopes.

Read sources:

- SPARQL over asserted source graphs for canonical facts.
- Current reasoning-result pointer when inferred statements are requested.
- Current rule-result pointer when deterministic derived statements are requested.
- Evidence and review graphs when provenance or audit details are requested.
- Graph-set metadata for version/scoping behavior.

Projection rules:

1. Neo4j is rebuilt from Oxigraph graph sets and current derived-result pointers.
2. Search and vector indexes are rebuilt from RDF labels, aliases, descriptions, evidence text
   references, catalog metadata, and selected statement annotations.
3. Frontend caches are invalidated from graph revision and projection job status.
4. Projection rebuild jobs record source graph set, source signature, current derived pointers,
   counts, and errors.
5. Projection failure does not mutate canonical RDF state, but it can block user-visible cutover
   if the affected screen depends on that projection.

## Parity Strategy

Parity compares legacy-derived behavior with RDF-derived behavior before old semantic writes are
disabled.

Parity checks should use semantic equivalence where ordering, serialization, blank-node ids, or
non-semantic timestamps differ. They should use exact equality where product behavior depends on a
stable value.

### Parity Test Matrix

| Area | Legacy source | RDF-derived source | Required checks |
| --- | --- | --- | --- |
| Ontology list/detail | Ontology tables | SPARQL/JSON projection | IDs, labels, descriptions, version status, graph set. |
| Classes | Class tables | `owl:Class` projection | Labels, aliases, hierarchy, properties, external mappings. |
| Properties | Property tables | OWL/RDFS/SHACL projection | Datatype, domain/range, required/single-valued flags, enum values. |
| Relation types | Relation metadata | Object-property and relation projection | Source/target classes, status, symmetric/transitive flags, labels. |
| Entities | Entity tables/Neo4j | RDF data graph projection | IDs, classes, labels, aliases, scalar properties. |
| Relations | Neo4j/current graph repos | RDF object properties and `op:Relation` | Source, target, type, status, relation id. |
| Fact claims | Fact/governance tables | `op:FactClaim` projection | Predicate, value, confidence, audit status, stale state. |
| Evidence | Evidence tables | Evidence graph and PROV-O projection | Evidence ids, source refs, links, missing-evidence flags. |
| Validation state | Validation run tables | Validation run graph plus summary | Conforms, shape version, report summary, graph set. |
| Reasoning state | Reasoning run/pointer tables | Reasoning run/result graphs plus pointer | Current result graph, stale state, consistency, inferred count. |
| Rule state | Rule/run tables | Rule run/result graphs plus pointer | Rule version, generated statements, warnings, audit status. |
| Catalog entries | Catalog tables | Catalog RDF projection | Source ids, labels, semantic type, project ownership. |
| Semantic mappings | Mapping tables | Mapping statements | Source field, target class/property/relation, confidence/status. |
| Connectors | Connector tables | RDF source metadata plus operational rows | Non-secret metadata parity; credentials excluded. |
| Identifier resolution | Resolver tables | Same-as/match projection | Canonical id, aliases, match confidence, provenance. |
| Product API reads | Current response JSON | RDF-backed compact JSON | Response shape and user-visible fields. |
| SPARQL/direct reads | N/A or sidecar | Oxigraph | Query correctness over migrated graph sets. |
| Neo4j visualization | Current Neo4j | Rebuilt Neo4j projection | Node/edge counts, labels, relation types, traversal samples. |
| Search/vector | Existing indexes | Rebuilt projections | Result ids, labels, ranking tolerance, warning metadata. |
| Export/import | Current export | RDF TriG/Turtle/JSON-LD | Parseability, key triples, round-trip compact projection. |

### Required Parity Gates

Cutover for a scope requires:

- no failed mandatory parity reports,
- no unsupported source object kinds in the migration inventory,
- SHACL validation success or an approved validation waiver,
- graph-derived product API parity for the screens and API routes in scope,
- Neo4j/search/vector projection rebuild success when the migrated scope depends on those
  projections,
- successful dual-write compare window for active write paths,
- rollback rehearsal in the same environment class.

## Shadow-Read and Dual-Write Strategy

Phase 7 should prefer shadow reads before dual writes for high-risk scopes.

Shadow-read mode:

```text
serve response from legacy
  -> compute RDF-derived response asynchronously or in bounded inline compare
  -> store diff report
  -> never expose RDF response unless explicitly requested
```

Dual-write mode:

```text
legacy write remains primary
  -> RDF write is attempted with the same command semantics
  -> affected read models are compared
  -> mismatch blocks cutover
```

RDF-primary mode:

```text
RDF write is primary
  -> legacy semantic write is blocked or maintained only as optional rollback snapshot
  -> product reads come from RDF-derived projections
```

Dual-write should be scoped and time-limited. The goal is to prove command compilers and parity,
not to run two permanent semantic sources of truth.

## Rollback Safeguards

Rollback is available until legacy semantic storage is decommissioned for the migrated scope.

Safeguards:

1. Keep legacy semantic tables read-only but intact during the rollback retention window.
2. Record the canonical mode change as operational metadata with actor, time, scope, and previous
   mode.
3. Keep the final pre-cutover source snapshot signature.
4. Do not delete shadow or migrated RDF graphs during immediate rollback; mark them inactive or
   superseded so they can be inspected.
5. Keep projection rebuild jobs reversible by rebuilding from legacy during rollback.
6. Block rollback if new RDF-primary writes cannot be represented in legacy storage, unless an
   explicit data-loss waiver and export archive are created.
7. Export affected RDF graphs as TriG before destructive cleanup or legacy removal.

Rollback sequence:

```text
freeze semantic writes for scope
  -> switch product write mode back to legacy_primary
  -> switch product read mode back to legacy
  -> rebuild Neo4j/search/vector projections from legacy sources if required
  -> mark RDF graph set and migration run rolled_back
  -> unfreeze semantic writes
  -> keep parity reports and RDF export archive for diagnosis
```

## Idempotent Rerun Behavior

Every migration batch must be safe to rerun.

Idempotency rules:

1. Batch identity is based on migration run id, object kind, sorted source ids, source hash, target
   graph IRIs, and Phase 2 mapping version.
2. Generated RDF uses stable IRIs and deterministic serialization where practical.
3. Replacing a graph fragment must remove or overwrite only statements owned by the migrated
   source ids and mapping version.
4. Batch reruns compare source hash and target hash before writing.
5. If the source hash is unchanged and the target hash matches, the batch is marked `skipped` or
   `succeeded` without mutation.
6. If source changed during a non-cutover run, create a new batch generation or migration run
   rather than silently mixing snapshots.
7. Graph revisions increment only when the committed target graph content changes.
8. Partial batch failure records enough metadata to retry only the failed batch.

Large graph replacement should use scoped graph fragments or source-owned statement annotations
instead of dropping a whole graph when unrelated batches share the graph.

## Deployment Sequencing

Recommended rollout:

1. Ship migration metadata tables and API endpoints behind admin-only access.
2. Run preflight and dry-run in development with representative seeded data.
3. Run shadow backfill in development and verify full parity.
4. Run projection rebuilds from RDF and compare Neo4j/search/vector outputs.
5. Enable shadow reads for selected local/staging scopes.
6. Enable dual-write compare for low-risk write paths.
7. Fix parity gaps in mapping, command compilers, or projections.
8. Rehearse rollback in staging after a successful cutover rehearsal.
9. Cut over one low-risk scope to RDF primary.
10. Monitor write errors, parity drift, validation state, projection job failures, and query
    latency.
11. Expand scope-by-scope until all semantic scopes are RDF primary.
12. Disable legacy semantic writes only after deprecation criteria are met.
13. Archive or remove old semantic storage in a later cleanup phase.

The migration should support mixed mode: some scopes can remain legacy while migrated scopes are
RDF primary. Product services must resolve canonical mode by scope, not by a single global
assumption, until the final migration is complete.

## Deprecation Criteria

Old semantic write paths may be disabled for a scope only when all criteria are true:

1. Shadow backfill completed successfully for the scope.
2. Mandatory parity checks passed.
3. Dual-write compare ran for the agreed write-path window with no unresolved mismatches.
4. Product reads in scope are served from RDF-derived projections.
5. Structured product writes in scope route to `CanonicalSemanticWriteService`.
6. Direct semantic edits and product writes produce the same graph delta shape for equivalent
   operations.
7. SHACL validation and platform checks pass for current source graphs.
8. Required reasoning/rule outputs are current or explicitly marked stale with user-visible status.
9. Neo4j/search/vector/frontend projections can be dropped and rebuilt from RDF state.
10. Rollback rehearsal succeeded in the target environment class.
11. Operational dashboards or logs can detect RDF write failures, projection failures, and parity
    drift.
12. A final RDF TriG export archive exists for the migrated scope.

After deprecation, legacy semantic write endpoints should return deterministic errors such as
`409 Conflict` or `410 Gone` with guidance to the canonical product or semantic endpoint. Legacy
read endpoints may remain as compatibility wrappers only if they read from RDF-derived projections.

## Failure Handling

Failure classes:

| Failure | Handling |
| --- | --- |
| Oxigraph unavailable | Pause migration; do not mutate legacy canonical state. |
| RDF parse failure | Fail batch; record source ids and generated payload sample. |
| SHACL failure | Fail or warn according to migration policy; block cutover unless waived. |
| Parity mismatch | Keep legacy canonical; block cutover; create parity report. |
| Projection rebuild failure | Keep canonical mode unchanged; retry projection job; block UI cutover if required. |
| Dual-write RDF failure | Keep legacy canonical in dual-write stage; block cutover. |
| RDF-primary write failure | Return write error; do not fall back silently to legacy writes. |
| Rollback failure | Keep write freeze until read/write mode is consistent or operator intervenes. |

## Test Plan

Phase 7 implementation must include backend tests. Documentation-only changes do not require test
execution.

Required test coverage when implementing:

1. Migration inventory includes schemas, entities, relations, fact claims, evidence, catalog
   mappings, connector metadata, and identifier-resolution semantics.
2. Phase 2 IRI mapping is reused exactly by migration output.
3. Dry-run produces deterministic batch plans and target hashes without writing Oxigraph graphs.
4. Shadow backfill writes expected named graphs and graph registry entries.
5. Batch rerun with unchanged source is idempotent and does not increment graph revisions.
6. Batch rerun after source change creates the expected new target graph content.
7. Product command compiler and direct semantic edit produce equivalent RDF deltas for matching
   operations.
8. Locked graph edits are rejected through both product and direct semantic paths.
9. Missing-evidence facts and warnings survive migration and product API reads.
10. Validation, reasoning, and rule result pointers remain separate from source graphs.
11. Parity reports detect missing, extra, and changed schema/data/evidence/catalog items.
12. Neo4j/search/vector projection rebuild jobs consume RDF graph sets and current pointers.
13. Cutover switches read/write mode only after mandatory gates pass.
14. Rollback restores legacy-primary read/write mode and marks the RDF graph set rolled back.
15. Legacy semantic write paths return deterministic errors after deprecation.

Suggested verification commands for implementation changes:

```bash
cd backend && uv run pytest
cd frontend && npm run build
cd frontend && npx playwright test
```

Frontend checks are required only when user-visible workflows or read screens change.
