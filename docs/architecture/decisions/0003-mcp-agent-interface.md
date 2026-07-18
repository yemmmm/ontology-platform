# ADR 0003: MCP Agent Interface

## Status

Accepted

## Context

External agents need ontology-backed graph context. Exposing database-shaped CRUD or raw Cypher would make agents depend on storage details and would create security and governance risks.

## Decision

Expose semantic MCP tools first:

- `search_entities`
- `get_entity`
- `find_related_entities`
- `validate_entity`
- `explain_entity`

Controlled write tools such as `create_entity` and `create_relation` may be added, but must validate against ontology definitions.

Do not expose raw Cypher or a general public graph query DSL in the first version. The backend may define an internal `GraphQuerySpec` to keep the design extensible.

## Consequences

The MCP interface stays stable and agent-oriented. Graph implementation details remain encapsulated behind backend services.

