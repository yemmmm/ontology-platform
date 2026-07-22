# ADR 0007: First-party Modeling Runtime Boundary

## Status

Accepted; R2.0-002 plan review PASS on 2026-07-22

## Context

ADR 0001 separates the semantic platform from external Agent frameworks, runtimes, memory, and
production orchestration. That decision protected deterministic semantic facts and prevented the
backend from becoming a generic Agent host.

The v1.1 Local workflow nevertheless depends on Claude Code Agent definitions, Hooks, Harnesses,
launchers, and summarizers that the project cannot control consistently. R2.0-001 proved that the
pinned Pi public RPC and Extension surfaces can run isolated modeling roles, structured tools,
external clarification, observable events, and stage summaries without forking Pi.

R2.0-002 therefore needs to decide whether a first-party modeling Runtime can be an official
product component without weakening ADR 0001's semantic authority boundary.

## Decision

The product repository will deliver a first-party **Pi Local Modeling Agent Runtime** as a component
separate from Semantic Platform Core.

- The Pi component owns model calls, role Sessions, Prompt/Workflow Package loading, structured
  tool dispatch, user clarification, local events, stage summaries, and child-process lifecycle.
- Semantic Platform Core continues to own Projects, Ontologies, Evidence, Build Sessions, Leases,
  Modeling Batches, validation, applied state, versions, audit, queries, authorization, and
  persistence.
- Pi uses the same supported REST/MCP contracts as any authorized modeling client. It receives no
  direct repository/database access and no bypass for validation, review binding, dry-run/apply,
  idempotency, workspace version, Evidence, or query verification.
- Pi Session and event types are local implementation details. They do not enter public platform
  APIs, database schemas, semantic models, or modeled customer ontologies.
- The first implementation is a repo-local command with headless RPC child processes. It is not a
  backend module, systemd service, remote worker, or generic Agent hosting framework.
- The Pi Workflow Package is the only actively maintained modeling method after R2.0-002. The old
  Claude modeling Runtime and its Formal/strict-eval paths retire after independent Pi acceptance.

ADR 0001 remains authoritative for Semantic Platform Core and external consumption Agents. This
ADR supersedes only the broader interpretation that the product repository itself can never
deliver or control the lifecycle of a modeling Agent Runtime outside the core.

## Consequences

- The project can observe and change the modeling workflow without waiting for Claude Code Hook or
  session contracts.
- Runtime failures do not become semantic facts. Recovery uses stable workflow artifacts and
  platform state, not hidden chat or Runtime memory.
- Replacing Pi later changes the first-party Runtime component and Workflow adapter, not Semantic
  Platform Core protocols.
- There is one supported Local modeling path after migration. Claude Local, fast-local,
  strict-eval, and Formal no longer impose compatibility constraints.
- Production hosting, remote execution, complete crash recovery, management UI, and Pi Formal need
  separate requirements if real modeling work later proves them necessary.

## Rejected alternatives

- **Continue external-Runtime-only delivery:** rejected because it preserves the observability and
  control problem that motivated v2.0.
- **Embed Pi in backend or add a permanent Runtime service:** rejected as unnecessary for current
  local modeling quality experiments.
- **Maintain shared Claude and Pi rule trees:** rejected because the user chose Pi as the sole
  maintained modeling method and does not want ongoing Claude compatibility cost.
