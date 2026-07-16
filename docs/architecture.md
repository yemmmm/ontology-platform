# Architecture

## Purpose

Ontology Platform provides a lightweight ontology layer for applications and agents. The MVP focuses on a custom schema model and structured graph data, not full RDF/OWL semantics or agent orchestration.

## Interaction Model

The platform operates with three distinct parties:

| Party | Role | Surface |
|-------|------|---------|
| **User** | Domain expert and governance decision-maker. Clarifies intent, audits facts, resolves conflicts, publishes versions, and performs approve/reject decisions when a workflow explicitly requires human review. | Review Workbench (UI) |
| **Agent** | Conversation driver and workflow orchestrator. Understands user intent, drives the ontology-builder Skill, reads platform state, and submits dry-run or apply modeling batches through MCP or HTTP. An Agent may apply a batch when its Build Session, Ontology Lease, workspace version, and deterministic validation are valid; it cannot approve/reject a governed review decision or publish a version. | MCP / HTTP API |
| **Platform** | Durable state authority and governance enforcer. Stores semantic state, evidence, modeling batches, proposals, and review state. Resolves the target workspace, runs deterministic validation, enforces idempotency and edit concurrency, records audit/version state, and manages the draft→published lifecycle. | FastAPI + PostgreSQL + RDF Dataset / Neo4j |

**Information production (build/modify ontology):**

```
User ──(natural language)──▶ Agent ──(MCP/HTTP: dry-run batch)──▶ Platform
                                      ◀──(normalized delta + validation)──┘
                                      │
                                      └──(MCP/HTTP: apply batch)─────▶ Platform
                                           (session + lease + version guards)  │
User ◀──(status/evidence/audit)── Agent ◀────(batch result)─────────────────────┘

Optional governed review path:
Agent ──(submit proposal)──▶ Platform ──(review task)──▶ User
Agent ◀───────(read decision)───── Platform ◀──(approve/reject)─┘
```

### R-004 Modeling Batch execution target

R-004 uses one Ontology-scoped submission protocol for `dry_run`, `apply_atomic`, and
`apply_partial`. The API and MCP adapters call the same application service:

```text
REST / MCP
    │
    ▼
Modeling Batch Service
    ├── Session + Lease + workspace-version guards
    ├── Modeling Command Handler registry
    ├── item_ref resolution + SCC dependency groups
    ├── deterministic Findings + partial fixed-point validation
    └── persisted operation plan + Ontology Write Fence
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
      Canonical RDF writer   Rule / Evidence / Audit
         RDF Dataset              PostgreSQL
              └──────────┬──────────┘
                         ▼
             terminal Attempt or recovery
```

The platform does not claim an atomic transaction across RDF and PostgreSQL. It persists a
deterministic plan before side effects, prevents concurrent writes with an Ontology Write Fence,
and converges uncertain outcomes forward under the original Attempt. Reasoning, rule execution,
search/vector projection, and other derived rebuilds are marked stale and remain outside the
synchronous R-004 request.

The implementation is anchored by migrations `0023_modeling_batches`,
`0024_modeling_result_cascade`, and `0025_backfill_workspaces`,
`ModelingBatchService`, the `ModelingCommandHandlerRegistry`, and one composite workspace-version
service shared by Build Context, Modeling Context, and the apply guard. The Build Context Debug UI
is a read-only observer of these records; it is never an execution or recovery trigger.

**Information consumption (query data):**

```
User ──(natural language question)──▶ Agent
                                        │
                                        ├──(MCP: search_entities, get_entity, graph_query)
                                        │        ▶ Platform ──▶ Neo4j
                                        │
                                        ◀───────── results ──────────┘
                                        │
User ◀──(answer in natural language)────┘
```

## Implemented MVP

```text
React/Vite UI
  Project/ontology management, ontology designer, graph manager,
  health view, and demo agent test view.

FastAPI HTTP API
  Health checks, project CRUD, ontology CRUD,
  class/property/relation-type CRUD, entity CRUD/query, relation create/list,
  JSON import/export, and demo agent-test endpoint.

PostgreSQL
  Metadata: projects, ontologies, classes, property definitions,
  relation types, constraints table, ontology versions table, API keys table.

Neo4j
  Knowledge graph instances, typed relationships, entity embeddings, and ANN vector index.

MCP
  FastMCP tools for search, get entity, related entities, validation,
  and entity explanation against real graph data.
```

## Data Model

Metadata in PostgreSQL:

- `Project`: top-level knowledge domain container.
- `Ontology`: schema definition inside a project.
- `Class`: domain object type, with aliases and optional parent class IDs.
- `PropertyDef`: property definition for a class.
- `RelationType`: typed relationship between source and target classes.
- `Constraint`: stored metadata placeholder; no custom rule engine is exposed.
- `OntologyVersion`: draft/published/deprecated states with schema snapshots and publication reports.
- `ApiKey`: stored metadata placeholder; no API key lifecycle UI is exposed.

Graph data in Neo4j:

```cypher
(:Entity:<normalized_class_label> {
  id,
  project_id,
  ontology_id,
  ontology_version_id,
  class_id,
  class_label,
  name,
  aliases,
  properties_json,
  embedding,
  embedding_model,
  embedding_dimensions,
  embedding_source_hash
})
```

```cypher
(:Entity)-[:<NORMALIZED_RELATION_TYPE> {
  id,
  project_id,
  ontology_id,
  ontology_version_id,
  relation_type_id,
  relation_type,
  properties_json
}]->(:Entity)
```

`properties_json` is decoded by the API/MCP layer so clients still see `properties` as JSON objects.
Embedding fields stay internal. Entity name, aliases, and canonical properties JSON are embedded with
Zhipu Embedding-3 and queried through a 1024-dimensional cosine ANN index. Dynamic Neo4j labels and
relationship types are normalized by the backend before use.

PostgreSQL remains authoritative for ontology metadata copied onto graph instances. Class and
relation-type updates propagate their normalized names to Neo4j. Metadata deletion is rejected while
graph instances still reference it. The graph-consistency API audits and repairs historical stale
labels/types; orphaned graph data is reported but never deleted automatically.

## Validation

Implemented validation covers:

- ontology and class existence
- class membership in the selected ontology
- parent class IDs belonging to the same ontology
- required entity properties
- unknown entity properties
- property types: `string`, `number`, `boolean`, `date`, `enum`, `reference`, `json`
- enum membership when `enum_values` are configured
- relation type membership in the selected ontology
- relation source and target entity existence
- source and target class compatibility, including subclass checks

Not implemented:

- custom constraint execution
- cross-entity consistency rules
- inference or reasoning
- cardinality enforcement beyond stored metadata placeholders

## Boundaries

HTTP and MCP may both expose Agent-initiated semantic writes, including R-004 modeling-batch dry-run
and apply. Batch application is a technical write action, not a human governance approval: the
platform authorizes it through the active Build Session, valid Ontology Lease, expected workspace
version, deterministic validation, idempotency, and the caller authorization introduced by R-008.
It does not require a separate human apply step.

Approve/reject decisions for workflows that explicitly require human review, publication, and
conflict resolution remain governance decisions and are not granted to the Agent by the modeling
batch protocol. Those decisions remain on controlled HTTP/UI surfaces. Raw Cypher and unrestricted
SPARQL Update are not exposed to the Agent.

## Implemented in v0.3

- Governed ontology version lifecycle: draft → published → deprecated, with immutable published snapshots
- Proposal-based workflow: Agent submits schema/entity/relation proposals; platform validates and tracks state
- Human review via Review Workbench: approve, reject, edit, merge, waive
- Publication readiness gates: schema validation, evidence coverage, competency question pass rate, fact audit
- Fact claim generation, stratified audit sampling, and stale invalidation on graph changes
- MCP semantic tools for Agent-driven build workflow (propose, validate, read state)
- Document ingestion with evidence tracking and untrusted-content boundaries
- Idempotency keys for safe Agent retry

## Planned Future Capabilities

- full user accounts, RBAC, or organization tenancy
- RDF/OWL/SHACL as the primary internal model
- external entity backends: entity data sourced from external databases or APIs
- entity-level external_mappings for cross-system data federation
- field-level data_source declarations with sensitivity and access policy metadata
- cross-system proxy query: platform routes Agent queries to external data sources
- graph inference, rule engines, or reasoning services
- multi-agent orchestration or agent lifecycle management

## R-006 Semantic Query Boundary

Agent-facing semantic reads use Project and one-or-more Ontology IDs, never Graph Set IDs or graph
IRIs. `SemanticQueryScopeResolver` resolves each ready Ontology's default workspace, current source
and shape graphs, and current reasoning/rule pointers. Project-wide resolution may exclude an
incomplete workspace with a partial-scope warning; an explicit Ontology list is all-or-nothing.

`SemanticContextQueryService` owns one bounded pipeline: normalize lexical terms, run an RDF-level
filtered candidate query, add current PostgreSQL Rule definitions, rank deterministically, expand a
bounded relation neighborhood, project current SHACL constraints, and reduce R-005 lineage to status
and Evidence Reference IDs. REST and MCP are adapters over this service. The pipeline has no intent
router, LLM, translation, answer planner, persistent search index, or Evidence full-text corpus.
Predicate labels may be read from another persisted graph of the same Ontology; internal graph-pair
bindings prevent an equal IRI or label in another Ontology from being joined to the wrong fact.

`ScopedSparqlQueryService` validates read-only query forms with RDFLib and rejects caller dataset or
federation clauses. It then scans only validated syntax boundaries, injects server-owned `FROM` and
`FROM NAMED` clauses at the query-form-specific top-level dataset position, and parses the scoped
query again before execution. The original query never executes when the insertion point is
ambiguous. This fail-closed path is required because Oxigraph 0.5.9 collapses repeated SPARQL
Protocol dataset parameters. Scope therefore remains effective for default patterns, `GRAPH ?g`,
and explicit graph clauses across one or multiple Ontologies. The same top-level scanner clamps the
executed solution LIMIT before a second parse; a type-aware response limiter then caps SELECT
bindings and CONSTRUCT/DESCRIBE triples, so caller LIMIT clauses cannot weaken either resource or
response bounds. The dataset intentionally excludes non-member custom and virtual generated SHACL
views; Context Query projects their merged guidance through the Shape Endpoint.
