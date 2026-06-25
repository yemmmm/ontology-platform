# Architecture

## Purpose

Ontology Platform provides a lightweight ontology layer for applications and agents. The MVP focuses on a custom schema model and structured graph data, not full RDF/OWL semantics or agent orchestration.

## Interaction Model

The platform operates with three distinct parties:

| Party | Role | Surface |
|-------|------|---------|
| **User** | Domain expert, governance decision-maker. Approves/rejects proposals, audits facts, resolves conflicts, publishes versions. | Review Workbench (UI) |
| **Agent** | Conversation driver, workflow orchestrator. Understands user intent, drives the ontology-builder Skill, submits proposals, reads platform state. Interacts with the platform exclusively through MCP tools and HTTP API. Cannot approve, reject, apply, or publish. | MCP / HTTP API |
| **Platform** | Durable state authority, governance enforcer. Stores schema, graph instances, evidence, proposals, and review state. Runs deterministic validation, manages version immutability, enforces the draft→published lifecycle. | FastAPI + PostgreSQL + Neo4j |

**Information production (build/modify ontology):**

```
User ──(natural language)──▶ Agent ──(MCP: propose/validate)──▶ Platform
                                                                  │
User ◀──(review link)──────── Agent ◀──(batch status)─────────────┘
  │
  └──(workbench: approve/reject)──▶ Platform (state updated)
                                       │
User ◀──(status update)── Agent ◀──(MCP: read state)──────────────┘
```

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

The HTTP API is the authoritative write boundary for governance decisions (approve, reject, publish, resolve conflicts). Raw Cypher is not exposed. MCP exposes semantic tools for both read operations (search, get entity, related entities, graph query, fact claims) and Agent-initiated write operations (submit proposals, validate proposals, propose entities/relations, save interview answers). Governance decisions that require explicit human authorization remain HTTP-only and are enforced through the Review Workbench.

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
