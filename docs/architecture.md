# Architecture

## Purpose

Ontology Platform provides a lightweight ontology layer for applications and agents. The MVP focuses on a custom schema model and structured graph data, not full RDF/OWL semantics or agent orchestration.

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
  Knowledge graph instances: Entity nodes and typed relationships.

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
- `OntologyVersion`: stored metadata placeholder; no version workflow is exposed.
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
  properties_json
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

`properties_json` is decoded by the API/MCP layer so clients still see `properties` as JSON objects. Dynamic Neo4j labels and relationship types are normalized by the backend before use.

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

The HTTP API is the write boundary for metadata and graph instances. Raw Cypher is not exposed. MCP exposes read/query/validation tools only; graph writes still go through controlled HTTP API endpoints.

## Planned Future Capabilities

These are not implemented in the MVP:

- full user accounts, RBAC, or organization tenancy
- RDF/OWL/SHACL as the primary internal model
- vector search or embedding indexes
- ontology version publishing and migration workflows
- automatic extraction from code, documents, schemas, or logs
- graph inference, rule engines, or reasoning services
- multi-agent orchestration or agent lifecycle management
