# ADR 0002: Storage Architecture

## Status

Accepted

## Context

The platform needs both ontology governance and graph-native querying.

Ontology definitions, platform metadata, audit data, API keys, import/export jobs, and future versioning fit relational storage well. Knowledge graph instances need native graph traversal and visualization support.

## Decision

Use a dual-storage architecture:

- PostgreSQL stores platform metadata and ontology definitions.
- Neo4j stores knowledge graph instances.

PostgreSQL is the source of truth for ontology definitions and governance metadata. Neo4j is the source of truth for entity nodes, relationship edges, and graph traversal.

## Consequences

Writes to graph instances must validate against ontology definitions before reaching Neo4j. Services should keep storage access behind repositories so future storage changes do not leak into API, MCP, or Web UI boundaries.

