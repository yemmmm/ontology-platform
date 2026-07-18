# ADR 0001: Platform Boundaries

## Status

Accepted

## Context

The platform should be reusable across different projects and should help external agents consume structured ontology and knowledge graph context.

The platform must not become tightly coupled to a specific agent framework, agent runtime, or model provider.

## Decision

The platform manages:

- projects as platform-side knowledge domain containers
- ontology schemas
- knowledge graph instances
- validation and import/export contracts
- MCP tools/resources for external consumption
- a demo agent test area for local validation

The platform does not manage:

- agent lifecycle
- agent deployment
- agent memory beyond graph data managed by this platform
- workflow orchestration for production agents

## Consequences

Agents consume the platform through MCP and do not become first-class platform-owned entities. A test agent may exist only to validate the ontology layer and MCP tool design.

