# Phase 6 Graph-Derived Product APIs and Projections

## Status

Detailed design. Phase 6 builds on the Phase 1 semantic runtime spine, the Phase 2 namespace and
export baseline, the Phase 3 governed direct semantic interfaces, the Phase 4 graph registry and
graph-set runtime state, and the Phase 5 reasoning, validation, and deterministic derivation
services.

Phase 6 does not switch canonical semantic writes to Oxigraph yet. That belongs to Phase 7. This
phase makes product reads, exports, traversal, search, and vector retrieval derive from RDF graph
sets so the platform can prove projection parity before the canonical migration.

## Goal

Make business-facing read APIs, UI read models, graph visualization, search, vector retrieval, and
standards exports derive from the RDF Dataset boundary.

The platform should be able to resolve a graph set, include the current reasoning and rule result
graphs when the view requires them, query Oxigraph, and return compact product JSON, JSON-LD,
Turtle, TriG, Neo4j projection data, search documents, and vector index documents without treating
Postgres, Neo4j, search, or vector stores as semantic sources of truth.

## Confirmed Decisions

1. Oxigraph RDF Dataset state is the semantic source boundary for graph-derived reads.
2. Neo4j is a rebuildable visualization and traversal projection only.
3. Search and vector indexes are rebuildable projections only.
4. Postgres stores operational metadata, projection job state, run pointers, settings, and
   non-semantic records. It does not store canonical RDF statements.
5. Compact business JSON is a read model compiled from SPARQL over graph sets, not a separate
   semantic model.
6. JSON-LD, Turtle, and TriG exports are standards-compatible read surfaces over the same graph-set
   inputs.
7. Product read models must surface provenance, evidence status, assertion kind, and derived-result
   staleness when they include graph statements.
8. Projection rebuild jobs are explicit, repeatable, and scoped by graph set, graph revisions,
   derived result pointers, projection kind, and projection version.
9. Graph visibility policy starts lightly in Phase 6, after the core query and edit path is stable.
   It must label and filter graph sets conservatively without becoming a full RBAC system.

## Non-Goals

- Do not migrate semantic source-of-truth writes from the legacy model to Oxigraph in Phase 6.
- Do not remove the existing product APIs before graph-derived parity is proven.
- Do not make Neo4j, search, vector indexes, frontend caches, or Postgres read tables authoritative
  semantic storage.
- Do not implement full role-based access control or a complete query security layer.
- Do not let product read APIs hide whether a statement is asserted, OWL-inferred,
  rule-derived, construct-derived, workflow-derived, imported, or stale.
- Do not introduce a second projection language when SPARQL, JSON-LD contexts, and Phase 5 rule
  outputs are sufficient.
- Do not rebuild every projection synchronously after every semantic edit in the first
  implementation.

## Execution Boundary

Phase 6 adds a read/projection layer beside the existing product services:

```text
FastAPI product and semantic read APIs
  -> SemanticReadModelService
     -> SemanticGraphSetService
     -> SemanticDerivedStateService
     -> RdfStoreRepository over Oxigraph
     -> SemanticProjectionJobService over Postgres metadata
     -> Neo4jProjectionWriter
     -> SearchProjectionWriter
     -> VectorProjectionWriter
```

The boundary rules are:

- graph-derived reads resolve a graph set first;
- graph-derived reads use current derived-result pointers rather than guessing latest run ids;
- read models may merge source and result graphs, but the response must preserve origin metadata;
- projection writers delete and rebuild their own projection scope from Oxigraph-derived input;
- failed projection writes must not mutate RDF source graphs;
- stale derived result pointers or stale projection jobs are visible in responses.

## Read Model Scope

Phase 6 introduces graph-derived read models incrementally. Start with the frontend screens and
agent tools that need parity before Phase 7:

| Read model | Input graph roles | Derived graphs | Output |
| --- | --- | --- | --- |
| Ontology schema summary | `asserted_ontology`, `shape` | optional reasoning | compact JSON, JSON-LD |
| Class detail | `asserted_ontology`, `shape` | optional reasoning | compact JSON, JSON-LD |
| Entity detail | `asserted_data`, `evidence` | reasoning and rules when requested | compact JSON, JSON-LD |
| Relation/fact list | `asserted_data`, `evidence` | rules when requested | compact JSON |
| Evidence-aware statement list | `asserted_data`, `evidence` | reasoning and rules when requested | compact JSON, JSON-LD |
| Graph visualization | ontology/data graph set | current reasoning/rule result pointers when enabled | Neo4j projection |
| Semantic search | ontology/data/evidence graphs | derived labels and classifications when current | search and vector docs |
| Export bundle | selected graph set | caller-selected derived graphs | Turtle, TriG, JSON-LD |

The first pass should cover a small set of key screens end to end before expanding to every
product view. The old read path may remain as the comparison baseline during Phase 6.

## Compact Business JSON Contract

Compact business JSON is the stable product-facing shape for UI screens and common agent tools.
It is not a write format and is not canonical storage.

Common envelope:

```json
{
  "graph_set_id": "working-version-123",
  "source_signature": "sha256:...",
  "projection_version": "semantic-read-v1",
  "derived_state": {
    "reasoning": {
      "status": "current",
      "run_id": "reasoning-run-1",
      "result_graph_iri": "http://ontology-platform.local/semantic/graph/reasoning-result/reasoning-run-1"
    },
    "rule": {
      "status": "stale",
      "run_id": "rule-run-1",
      "result_graph_iri": "http://ontology-platform.local/semantic/graph/rule-result/rule-run-1"
    }
  },
  "warnings": [
    {
      "code": "stale_rule_result",
      "message": "Rule-derived statements are stale for this graph set."
    }
  ],
  "items": []
}
```

Every statement-bearing item must include:

```json
{
  "id": "statement-or-resource-id",
  "iri": "http://example.test/entity/alice",
  "label": "Alice",
  "source_graph_iri": "http://ontology-platform.local/semantic/graph/data/demo",
  "assertion_kind": "asserted",
  "evidence_status": "supported",
  "evidence_ids": ["evidence-1"],
  "provenance": {
    "generated_by": "semantic-edit-audit-1",
    "run_id": null,
    "actor": "agent-or-user",
    "timestamp": "2026-07-05T00:00:00Z"
  },
  "audit_status": "system_accepted",
  "staleness": {
    "is_stale": false,
    "reason": null
  }
}
```

Allowed `assertion_kind` values:

- `asserted`
- `imported`
- `owl_inferred`
- `rule_derived`
- `construct_derived`
- `workflow_derived`
- `validation_report`
- `policy_metadata`
- `review_metadata`

Allowed evidence status values should reuse the Phase 2 and Phase 5 vocabulary:

- `supported`
- `missing_evidence`
- `derived_from_missing_evidence`
- `not_applicable`
- `unknown`

Read APIs that merge source and derived graphs must include `assertion_kind`, `source_graph_iri`,
and staleness information by default. Callers may request a smaller field set, but the backend
must not silently collapse asserted and derived statements into the same unlabelled value.

## JSON-LD Contract

JSON-LD responses use the Phase 2 context as the base context and add projection metadata terms:

```json
{
  "@context": [
    "http://ontology-platform.local/semantic/context/platform.jsonld",
    {
      "projection": "http://ontology-platform.local/semantic/vocab/projection/",
      "assertionKind": "projection:assertionKind",
      "sourceGraph": "projection:sourceGraph",
      "evidenceStatus": "projection:evidenceStatus",
      "derivedState": "projection:derivedState",
      "isStale": "projection:isStale"
    }
  ],
  "@id": "http://ontology-platform.local/semantic/entity/alice",
  "assertionKind": "asserted",
  "sourceGraph": "http://ontology-platform.local/semantic/graph/data/demo",
  "evidenceStatus": "supported"
}
```

JSON-LD read endpoints should support:

- `profile=compacted|expanded`;
- `include=asserted|reasoning|rules|full-working-view`;
- `allow_stale_derived=true|false`;
- `graph_set_id=...`;
- `context=platform|interop`.

The compacted profile is optimized for application consumption. The expanded profile is for
interop and debugging. Both profiles must preserve named graph origin through explicit properties
or JSON-LD named graph structures.

## Turtle and TriG Export Contract

Turtle is used for single-graph or merged inspection exports. TriG is used for dataset exports
where graph boundaries matter.

`GET /api/semantic/graph-sets/{graph_set_id}/export?format=trig`

Default behavior:

- exports asserted ontology/data graphs in their original named graph boundaries;
- includes evidence and shape graphs when requested;
- includes current reasoning and rule result graphs only when requested or when the selected export
  profile requires the full working view;
- includes graph metadata, run metadata, and projection metadata graphs only when
  `include_metadata=true`;
- returns warnings when requested derived graphs are stale or missing.

Request parameters:

```text
format=trig|turtle|json-ld
include=asserted|asserted-plus-reasoning|asserted-plus-rules|full-working-view
include_evidence=true|false
include_shapes=true|false
include_policy=true|false
include_metadata=true|false
allow_stale_derived=true|false
```

TriG exports should keep named graph IRIs intact. Turtle exports should require either a single
graph or an explicit merged-view profile so callers cannot accidentally lose graph boundaries.

## API Surface

Phase 6 extends `/api/semantic/...` and may add product-route compatibility endpoints only where a
screen is intentionally migrated to graph-derived reads.

`GET /api/semantic/graph-sets/{graph_set_id}/read-models/{model_name}`

Returns compact business JSON for a named read model.

Query parameters:

```text
include=asserted|asserted-plus-reasoning|asserted-plus-rules|full-working-view
allow_stale_derived=true|false
field_set=summary|detail|audit
limit=...
cursor=...
```

`GET /api/semantic/resources/{resource_iri:path}`

Returns one resource as compact JSON or JSON-LD.

`GET /api/semantic/statements`

Returns statement-level read rows with origin, evidence, provenance, assertion kind, and staleness.

`GET /api/semantic/graph-sets/{graph_set_id}/export`

Returns Turtle, TriG, or JSON-LD export.

`POST /api/semantic/projection-jobs`

Creates a projection rebuild job.

Request:

```json
{
  "graph_set_id": "working-version-123",
  "projection_kind": "neo4j",
  "projection_version": "neo4j-v1",
  "include": "full-working-view",
  "allow_stale_derived": false,
  "mode": "rebuild"
}
```

`GET /api/semantic/projection-jobs/{job_id}`

Returns job status, input signature, result counts, warnings, and errors.

`POST /api/semantic/projection-jobs/{job_id}:run`

Runs a queued job synchronously in development or dispatches it to the configured worker in
production.

`POST /api/semantic/projections:reconcile`

Marks projection jobs stale when their graph-set source signature, input derived pointers,
projection version, index configuration, or projection writer version changes.

`GET /api/semantic/projections/status`

Returns projection freshness by graph set and projection kind.

## Postgres Metadata Design

Extend or replace the Phase 1 `semantic_projection_jobs` table with graph-set-aware fields:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key and job id. |
| `graph_set_id` | string FK | Graph set being projected. |
| `projection_kind` | string | `business_json`, `neo4j`, `search`, `vector`, or `export_cache`. |
| `projection_version` | string | Version of the mapping/query/writer contract. |
| `projection_scope` | string | `asserted`, `asserted_plus_reasoning`, `asserted_plus_rules`, or `full_working_view`. |
| `source_signature` | string | Graph-set source signature consumed by the job. |
| `input_graph_revisions` | JSONB | Graph IRI to revision map. |
| `input_derived_pointers` | JSONB | Reasoning/rule pointer ids and statuses consumed by the job. |
| `target_store` | string nullable | `neo4j`, `postgres_cache`, `search`, `vector`, or external index name. |
| `target_partition` | string nullable | Project/version/index partition cleared and rebuilt by the job. |
| `status` | string | `pending`, `running`, `succeeded`, `failed`, `stale`, or `superseded`. |
| `node_count` | int nullable | Neo4j nodes or projected resources. |
| `relationship_count` | int nullable | Neo4j relationships. |
| `document_count` | int nullable | Search/vector documents. |
| `started_at` / `finished_at` | timestamptz nullable | Runtime bookkeeping. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Warnings, writer version, index config hash, and smoke-check details. |

Add `semantic_projection_manifests` when a projection produces durable target partitions:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `graph_set_id` | string FK | Projected graph set. |
| `projection_kind` | string | Projection kind. |
| `active_job_id` | string FK | Last successful active job. |
| `source_signature` | string | Source signature represented by the active projection. |
| `projection_version` | string | Mapping version represented by the active projection. |
| `target_partition` | string | Target partition, label, index, or namespace. |
| `status` | string | `current`, `stale`, `failed`, or `disabled`. |
| `updated_at` | timestamptz | Last manifest update. |
| `metadata` | JSONB | Counts, warnings, index settings, and visibility labels. |

Projection manifests are operational pointers. They do not make the target store canonical.

## Service Design

Add service boundaries:

```text
SemanticReadModelService
  -> resolve graph set and read scope
  -> choose SPARQL templates
  -> execute bounded read queries
  -> attach origin, evidence, provenance, and staleness metadata
  -> return compact JSON or JSON-LD

SemanticExportService
  -> resolve export profile
  -> fetch graph content from Oxigraph
  -> preserve graph boundaries for TriG
  -> compact JSON-LD with selected context
  -> return warnings for stale or missing derived graphs

SemanticProjectionJobService
  -> create projection jobs
  -> snapshot source signatures, graph revisions, and derived pointers
  -> dispatch or run projection rebuilds
  -> update manifests and staleness status

Neo4jSemanticProjectionService
  -> build node and relationship rows from RDF graph sets
  -> clear target partition
  -> write visualization/traversal projection
  -> verify counts and sample traversals

SemanticSearchProjectionService
  -> build search documents for labels, aliases, definitions, notes, evidence, and descriptions
  -> write full-text index partitions
  -> expose freshness metadata

SemanticVectorProjectionService
  -> build embedding input documents from semantic resources and evidence context
  -> write vector index partitions
  -> record model, embedding config, and source signature
```

Extend `RdfStoreRepository` with bounded helpers:

```python
query_read_model(
    query: str,
    graph_iris: list[str],
    timeout_seconds: float,
    limit: int,
) -> SparqlResult

export_graph_set(
    graph_iris: list[str],
    format: RdfFormat,
) -> str
```

The repository still owns Oxigraph protocol concerns. It should not know product-specific JSON
field names or projection target schemas.

## SPARQL Template Policy

Read models use versioned SPARQL templates owned by the backend. Phase 6 should avoid accepting
arbitrary product-read SPARQL from UI routes.

Template requirements:

- declare required graph-set roles;
- declare whether current reasoning or rule result graphs are required;
- declare result limits and sort keys;
- include graph IRI and statement-origin bindings where statement rows are returned;
- bind assertion kind from graph category, statement annotations, or result pointer metadata;
- bind evidence status from statement annotations or evidence graph references;
- return stable resource IRIs and compact IDs.

Caller-provided SPARQL remains available through the direct semantic query endpoint from earlier
phases. Product read models should use reviewed templates so UI behavior is predictable and testable.

## Neo4j Projection

Neo4j projection is optimized for graph visualization and high-speed traversal. It is not
authoritative semantic storage.

Projection partitioning:

- use one partition per graph set and projection version;
- tag every node and relationship with `graph_set_id`, `source_signature`, and
  `projection_job_id`;
- clear only the target partition before rebuild;
- keep the previous successful partition active until the new partition passes verification where
  practical.

Node shape:

```json
{
  "iri": "http://ontology-platform.local/semantic/entity/alice",
  "kind": "entity",
  "labels": ["Student"],
  "display_label": "Alice",
  "class_iris": ["http://ontology-platform.local/semantic/class/student"],
  "assertion_kind": "asserted",
  "evidence_status": "supported",
  "source_graph_iri": "http://ontology-platform.local/semantic/graph/data/demo",
  "is_stale": false
}
```

Relationship shape:

```json
{
  "iri": "http://ontology-platform.local/semantic/relation/r1",
  "type_iri": "http://ontology-platform.local/semantic/relation-type/enrolled-in",
  "source_iri": "http://ontology-platform.local/semantic/entity/alice",
  "target_iri": "http://ontology-platform.local/semantic/entity/course-1",
  "assertion_kind": "asserted",
  "evidence_status": "supported",
  "source_graph_iri": "http://ontology-platform.local/semantic/graph/data/demo",
  "is_stale": false
}
```

Neo4j write flow:

```text
create projection job
  -> resolve graph set and current derived pointers
  -> reject or warn on stale derived inputs according to request
  -> query Oxigraph for nodes and relationships
  -> clear target partition
  -> batch write nodes and relationships
  -> verify counts and sample traversal
  -> promote projection manifest to current
```

Graph visualization APIs should read only from the Neo4j projection manifest marked `current`.
If no current projection exists, return a rebuild-required status instead of falling back to
Neo4j as though it were canonical.

## Search and Vector Projections

Search and vector projections share the same rebuild discipline as Neo4j.

Search documents should include:

- resource IRI and compact ID;
- resource kind;
- labels, aliases, definitions, descriptions, and notes;
- class and relation type labels;
- evidence text snippets or evidence summaries where allowed;
- assertion kind and source graph IRI;
- evidence status and missing-evidence warnings;
- provenance run ids for derived labels/classifications;
- graph set id, source signature, projection job id, and projection version.

Vector documents should include:

- deterministic document id from graph set id, resource IRI, section kind, and projection version;
- embedding text assembled from labels, aliases, descriptions, evidence summaries, and selected
  neighboring semantic context;
- source graph IRIs and evidence ids used to build the text;
- embedding model and embedding configuration hash;
- assertion kind and staleness flags;
- visibility labels from the light graph visibility policy.

Projection rebuilds must be idempotent for the same source signature and projection version. If an
embedding provider or model changes, the vector projection version or embedding config hash must
change and the manifest becomes stale.

## Projection Rebuild Jobs

Projection jobs are explicit and repeatable.

Staleness triggers:

- graph-set source signature changes;
- source graph revision changes;
- current reasoning pointer changes when the projection scope includes reasoning;
- current rule pointer changes when the projection scope includes rules;
- a consumed derived pointer becomes stale;
- projection version changes;
- SPARQL template version changes;
- Neo4j writer, search mapping, vector model, or embedding config changes;
- graph visibility labels or policy graph membership changes.

Rebuild modes:

- `dry_run`: computes inputs, expected target partition, and result counts where possible;
- `rebuild`: clears and rewrites the target partition;
- `rebuild_side_by_side`: writes a new partition and promotes it only after verification;
- `reconcile`: updates staleness states without writing target stores.

Jobs should be safe to retry. A failed job must record whether it failed before target mutation,
during target mutation, or after target mutation verification.

## Light Graph Visibility Policy

Phase 6 starts policy-aware graph visibility only after the direct query/edit path and graph-set
projection path are stable.

Minimum policy:

- graph sets may carry visibility labels such as `internal`, `restricted`, or `public`;
- evidence graphs may carry masking or restricted-source labels;
- read-model requests can pass a visibility context;
- product read APIs filter or redact evidence text according to labels;
- exports include visibility warnings when restricted graphs are omitted;
- projection jobs record the visibility context used to build search/vector documents.

This is not full RBAC. It is a conservative label/redaction layer that prevents obvious leakage in
new read surfaces while leaving complete authorization and query-policy enforcement to later work.

## Staleness and Warning Semantics

Read APIs must return warnings when:

- a requested reasoning or rule pointer is stale;
- a requested derived result graph is missing;
- a projection manifest is stale or absent;
- the caller requested `allow_stale_derived=false` and the view cannot be served without stale
  derived statements;
- statements depend on missing-evidence inputs;
- graph visibility labels caused omitted graphs, redacted evidence text, or reduced search/vector
  context.

Default behavior should be conservative:

- compact product JSON may return asserted-only data when derived graphs are stale, but it must
  label the response scope and warnings;
- graph-derived views that require derived facts should fail with a deterministic client error when
  stale derived results are not allowed;
- export requests should include only current derived graphs unless the caller explicitly allows
  stale derived graphs.

## MCP Surface

Add MCP tools only for stable agent workflows:

- read a compact graph-derived resource or read model;
- export a graph set as JSON-LD, Turtle, or TriG;
- inspect projection freshness for a graph set;
- request a projection rebuild job;
- inspect provenance, evidence status, assertion kind, and staleness for a statement.

Do not expose projection writer internals or unrestricted target-store mutation tools through MCP.

## Test Strategy

Default backend tests should use fake RDF stores, fake projection writers, and deterministic
SPARQL result fixtures. They should not require live Oxigraph, Neo4j, search, vector stores, or an
embedding provider.

Required tests:

- compact business JSON read models include graph set id, source signature, assertion kind,
  evidence status, provenance, and staleness fields;
- read models include current reasoning/rule result graphs only through derived-result pointers;
- stale derived pointers produce warnings or deterministic failures according to
  `allow_stale_derived`;
- JSON-LD responses use the platform context and preserve source graph origin;
- Turtle export rejects ambiguous multi-graph exports unless a merged profile is requested;
- TriG export preserves named graph boundaries;
- projection jobs snapshot graph revisions, source signatures, derived pointers, and projection
  versions;
- projection reconciliation marks jobs and manifests stale after source graph or derived pointer
  changes;
- Neo4j projection writer clears only the target partition and records counts;
- graph visualization reads only from a current Neo4j projection manifest;
- search/vector document builders include evidence, provenance, assertion kind, staleness, and
  visibility labels;
- failed projection jobs do not mark manifests current;
- default `cd backend && uv run pytest` remains independent of live external services.

Optional integration or smoke checks:

- export a small graph set from live Oxigraph as TriG and JSON-LD;
- rebuild a tiny Neo4j projection and verify sample traversal;
- rebuild a tiny search/vector fixture with local fake embedding output;
- compare one frontend screen against old and graph-derived read models.

## Implementation Order

1. Add graph-set read scope resolver for asserted, asserted plus reasoning, asserted plus rules,
   and full working view.
2. Add versioned SPARQL templates for the first compact business JSON read models.
3. Add `SemanticReadModelService` and read-model API endpoints with origin, evidence, provenance,
   and staleness metadata.
4. Add JSON-LD resource/read-model responses using the Phase 2 context plus projection metadata.
5. Add graph-set export service for Turtle, TriG, and JSON-LD.
6. Extend projection job metadata and add projection manifests.
7. Implement projection staleness reconciliation.
8. Implement Neo4j rebuild jobs from Oxigraph-derived node/relationship rows.
9. Switch graph visualization reads to current Neo4j projection manifests.
10. Implement search document projection and freshness status.
11. Implement vector document projection with embedding config/version tracking.
12. Add light visibility labels/redaction for read models, exports, search, and vector documents.
13. Add MCP tools for stable read/export/projection status workflows.
14. Add focused service/API tests and optional smoke checks.

## Implementation Checklist

### 0. Documentation

- [ ] Keep this document linked from `semantic-language-refactor-plan.md` when Phase 6 is scheduled.
- [ ] State that Phase 6 migrates reads and projections, not canonical writes.
- [ ] Preserve the Oxigraph source boundary and rebuildable projection stance.

### 1. Read Scope and Templates

- [ ] Add graph-set read scope resolver.
- [ ] Add SPARQL template registry with template versions and required graph roles.
- [ ] Add bounded query execution for read models.
- [ ] Add origin, assertion-kind, evidence, provenance, and staleness binding helpers.

### 2. Compact Business JSON

- [ ] Add compact read-model schemas.
- [ ] Add read-model API endpoints.
- [ ] Implement schema summary, class detail, entity detail, and statement list as first models.
- [ ] Include derived-state warnings in every graph-derived response.

### 3. JSON-LD and Export

- [ ] Extend JSON-LD context with projection metadata terms.
- [ ] Add compacted and expanded JSON-LD response profiles.
- [ ] Add graph-set Turtle/TriG/JSON-LD export endpoint.
- [ ] Preserve graph boundaries in TriG exports.
- [ ] Reject ambiguous Turtle exports without an explicit merged profile.

### 4. Projection Jobs

- [ ] Extend `SemanticProjectionJobModel` for graph-set-aware jobs.
- [ ] Add `SemanticProjectionManifestModel`.
- [ ] Add projection job create/read/run endpoints.
- [ ] Add projection freshness status endpoint.
- [ ] Add reconciliation for source signatures, derived pointers, template versions, and writer
      versions.

### 5. Neo4j Projection

- [ ] Build Neo4j node and relationship rows from graph-derived SPARQL queries.
- [ ] Clear only the target graph-set partition before rebuild.
- [ ] Batch write nodes and relationships with source signature metadata.
- [ ] Verify counts and sample traversal before manifest promotion.
- [ ] Make graph visualization read only from current projection manifests.

### 6. Search and Vector Projection

- [ ] Build search documents from labels, aliases, definitions, descriptions, notes, evidence, and
      semantic context.
- [ ] Build vector documents with deterministic ids and embedding config hashes.
- [ ] Record model/index configuration in projection job metadata.
- [ ] Mark projections stale when model, mapping, source signature, or visibility context changes.

### 7. Visibility

- [ ] Add light graph-set and evidence visibility labels.
- [ ] Apply evidence redaction to read models and exports.
- [ ] Record visibility context in search and vector projection manifests.
- [ ] Return warnings when visibility policy omits or redacts graph content.

### 8. MCP and Tests

- [ ] Add MCP tools for graph-derived read models, export, projection freshness, rebuild request,
      and statement provenance inspection.
- [ ] Add service tests for read-model contracts, export behavior, projection staleness, and
      projection job state.
- [ ] Add API tests for read models, exports, projection jobs, and projection status.
- [ ] Keep default backend tests independent of live Oxigraph, Neo4j, search, vector stores, and
      embedding providers.
- [ ] Run `cd backend && uv run pytest` after behavior changes are implemented.

## Acceptance Criteria

- Key frontend read screens can be backed by compact business JSON derived from graph sets.
- Standard semantic read interfaces are available for graph sets: SPARQL, JSON-LD, Turtle, and
  TriG.
- Product read responses expose provenance, evidence status, assertion kind, and derived-result
  staleness.
- Neo4j graph visualization reads from projection data only and never treats Neo4j as canonical
  semantic storage.
- Neo4j, search, and vector projections can be dropped and rebuilt from Oxigraph graph-set state.
- Projection jobs are explicit, repeatable, statused, and stale when their semantic or projection
  inputs change.
- Search and vector documents carry source signatures, projection versions, evidence/provenance,
  visibility labels, and staleness state.
- Light graph visibility policy is present for new read surfaces without becoming full RBAC.
- Tests or smoke checks cover projection rebuild paths before Phase 7 canonical migration.

## Rollout Guidance

Use Phase 6 as a parity and confidence phase.

Recommended rollout:

1. Build graph-derived read models beside the old read APIs.
2. Compare old and graph-derived outputs for selected schemas, entities, facts, evidence, and
   derived statements.
3. Enable graph-derived reads for one low-risk frontend screen or agent tool.
4. Add projection manifests and rebuild status before switching graph visualization.
5. Rebuild Neo4j from Oxigraph and make graph visualization depend on the current projection
   manifest.
6. Rebuild search and vector projections from the same graph-set inputs.
7. Run parity tests and targeted UI smoke checks.
8. Keep old read paths available until Phase 7 migration readiness criteria are met.

Rollback is operationally simple because Phase 6 projections are rebuildable. Disable the
graph-derived read flag or projection manifest, keep canonical write paths unchanged, and rebuild
the projection after fixing the mapping, template, or writer.

## Completion Criteria

- [ ] `cd backend && uv run pytest`
- [ ] Selected compact business JSON read models are graph-derived and parity-checked.
- [ ] JSON-LD, Turtle, and TriG graph-set exports are available.
- [ ] Projection job and manifest metadata record source signatures, graph revisions, derived
      pointers, projection versions, and target partitions.
- [ ] Neo4j visualization reads from current projection manifests only.
- [ ] Search/vector projections are rebuildable and freshness-aware.
- [ ] Read models and projections surface provenance, evidence status, assertion kind, staleness,
      and visibility warnings.
