# Standard Semantic-Language Refactor Coding Plan

## Source

- Governing ADR: `docs/adr/0004-semantic-web-first-refactor-target.md`
- Phase 0 foundation output: `docs/semantic/phase0-technical-foundation.md`
- ADR status: Proposed
- Planning date: 2026-07-04

## Current Progress

- Phase 0 technical route: decided and documented.
- Implementation: not started.
- Current platform state: existing custom ontology/domain model with PostgreSQL and Neo4j-backed
  behavior remains in place.
- Target platform state: canonical semantic state is an RDF Dataset in an RDF-native store, with
  governed semantic edits, SHACL validation, OWL reasoning, and rebuildable projections.

This plan is for the standard semantic-language refactor. Phase 0 is not a shipped version; it is
the technical-route stage inside this refactor. Later phases implement that route incrementally.

## Phase 0 Foundation Summary

The agreed foundation is:

```text
FastAPI
  -> Oxigraph: canonical RDF dataset, named graphs, SPARQL query/update
  -> OWL reasoner: full OWL 2 DL reasoning over selected graph sets
  -> pySHACL: backend SHACL validation
  -> Neo4j: visualization/traversal projection rebuilt from RDF data
  -> Postgres: operational state, jobs, settings, pointers, and non-semantic records
```

Key Phase 0 decisions:

1. Use URL-shaped stable IRIs for semantic resources.
2. Use RDF Dataset and named graphs as the canonical semantic storage model.
3. Run Oxigraph as an independent RDF service, not as an embedded FastAPI-local store.
4. Keep Neo4j as a rebuildable property-graph projection for visualization and traversal only.
5. Run SHACL validation in a FastAPI backend validation service with `pyshacl` or equivalent.
6. Add a separate OWL reasoning service. HermiT is the baseline candidate; Openllet is an
   evaluation candidate.
7. Keep asserted source graphs and derived result graphs separate:
   `ontology`, `data`, `reasoning-result`, and `rule-result` are different graph boundaries.
8. Keep only the current effective reasoning result graph by default; older reasoning result graphs
   can be garbage-collected after a newer run succeeds.
9. Give agents a direct SPARQL query endpoint for flexible reads.
10. Support constrained SPARQL Update through the governed semantic edit endpoint for complex writes.
11. Semantic writes must pass parsing, graph-delta calculation where practical, SHACL/platform
    validation, graph editability checks, and audit.
12. Each actual graph has its own editability switch. There is no draft/published graph workflow.
13. Phase 0 does not implement full query security, graph visibility policy, RBAC, or permissions.
14. Missing-evidence facts may be written, but they must carry explicit evidence status and warnings.
15. Protégé/WebProtégé is not platform core and is not integrated in Phase 0; interoperability is
    preserved through standard RDF/OWL formats.

## Extension Hooks

These are intentionally not required for the first implementation pass, but the design must not
block them:

1. OWL reasoner execution can start as a command/service wrapper and later become a dedicated
   long-running service.
2. Reasoning can start as manual or agent-triggered execution and later become async/background
   recomputation after semantic edits.
3. Constrained SPARQL Update can start with delta-friendly forms such as `INSERT DATA`,
   `DELETE DATA`, and restricted `DELETE/INSERT WHERE`, then expand after audit and validation are
   stable.
4. Neo4j projection can start as explicit/manual projection and later become event-driven or
   background rebuild.
5. Postgres can start with operational metadata and pointers, then shrink further as semantic
   provenance and graph-native metadata mature.

## Phase 1: RDF-Native Service Foundation

Goal: establish the runtime skeleton for the selected semantic stack without replacing existing
product behavior yet.

Tasks:

1. Add configuration for Oxigraph service URL, default base IRI, and semantic graph settings.
2. Add an RDF store boundary in the backend for parsing, loading, querying, updating, and exporting
   named graphs.
3. Add a minimal Oxigraph-backed API surface:
   load/parse dataset, SPARQL query, SHACL validate, OWL reason, semantic edit, graph editability
   toggle, and export.
4. Add the backend SHACL validation service over data and shape graphs loaded from Oxigraph.
5. Add the OWL reasoning service wrapper over selected graph sets.
6. Add a minimal Neo4j projection proof sourced from Oxigraph.
7. Store operational metadata in Postgres where needed:
   jobs, validation runs, reasoning runs, current effective reasoning result pointer, and service
   settings.

Acceptance criteria:

- A small TriG dataset can be loaded into Oxigraph and exported again.
- Caller-provided SPARQL can query named graphs.
- SHACL validation returns a validation report from backend service execution.
- OWL reasoning returns consistency/classification/entailment output and can persist a
  reasoning-result graph.
- Neo4j can be populated from a small RDF graph projection.
- Locked graph edits return failure without mutation.

## Phase 2: Semantic Mapping and Compatibility Export

Goal: prove that the current platform model can be represented in RDF/OWL/SKOS/SHACL before
changing the canonical write path.

Tasks:

1. Add stable semantic IRIs to current domain objects.
2. Add JSON-LD context definitions for platform resources, graph IDs, labels, evidence status,
   audit fields, graph editability, validation, rules, and reasoning metadata.
3. Export current ontology schemas as RDF/OWL/SKOS.
4. Export current graph data, evidence, provenance, and fact claims as RDF.
5. Generate SHACL shapes from current class, property, relation, and constraint definitions.
6. Add round-trip tests:
   current schema -> RDF/OWL/SHACL -> business JSON projection.

Acceptance criteria:

- Current ontology schemas can be exported as Turtle, TriG, and JSON-LD.
- SHACL shapes can be generated from current definitions.
- Exported RDF preserves the business-visible schema and data needed by existing screens.
- Exported files can be inspected by standards-compatible tools without requiring Protégé
  integration.

## Phase 3: Governed Semantic Query and Edit Interfaces

Goal: make direct semantic access first-class while keeping platform governance deterministic.

Tasks:

1. Add the agent-facing SPARQL query endpoint over Oxigraph.
2. Add semantic edit ingestion for Turtle, TriG, JSON-LD, and constrained SPARQL Update.
3. Parse semantic edits into graph deltas where practical.
4. Reject writes to locked actual graphs.
5. Validate candidate post-edit graphs with SHACL and platform checks.
6. Record edit audit metadata:
   actor, time, reason, input format, target graph, validation result, and graph delta.
7. Allow fact writes without evidence only when explicit missing-evidence status is attached.
8. Apply valid edits directly to editable actual graphs.

Acceptance criteria:

- Agents can query complex graph state through SPARQL without chaining many fixed APIs.
- Agents and expert tools can submit direct semantic edits.
- Invalid edits and locked-graph edits do not mutate canonical semantic data.
- Semantic edit audit records are available.
- Missing-evidence facts are written with warnings rather than silently treated as verified facts.

## Phase 4: Named-Graph Governance and Versioning

Goal: move semantic governance into graph-native boundaries.

Tasks:

1. Introduce named graph storage for:
   ontology, data, evidence, policy, review/audit, validation, rule run/result, reasoning
   run/result, import, and optional proposal metadata.
2. Represent a version as a graph set made of actual ontology/data graphs plus governance graphs.
3. Replace draft/published promotion with per-graph editability.
4. Store statement-level metadata with RDF-star/RDF 1.2 reification or named graph metadata.
5. Keep OWL reasoning results in reasoning-result graphs, never in source ontology/data graphs.
6. Keep business rule results in rule-result graphs, never in source data graphs.
7. Add staleness detection for reasoning and rule results when source graphs or engine versions
   change.

Acceptance criteria:

- Actual graphs can be locked/unlocked independently.
- Source assertions, OWL-inferred statements, and business-rule-derived statements remain
  distinguishable.
- Current effective reasoning result pointers are maintained.
- Superseded reasoning result graphs can be garbage-collected.
- Audit/status reporting operates on graph deltas, editability state, validation state, and derived
  result staleness.

## Phase 5: Reasoning, Validation, and Deterministic Rules

Goal: make semantic consistency, structural validation, and business derivation explicit platform
services.

Tasks:

1. Use OWL reasoning for ontology consistency, class/property hierarchy classification,
   realization, and entailment checks.
2. Use SHACL for structural validation, datatype/cardinality checks, required fields, enum-like
   constraints, property shapes, and UI/form generation.
3. Keep OWL reasoning separate from SHACL validation and business rule execution.
4. Support SPARQL CONSTRUCT for simple graph-derived assertions where useful.
5. Define a restricted Datalog-like or platform DSL for explainable business rules if SPARQL
   CONSTRUCT is not enough.
6. Keep workflow/state-machine rules separate from semantic inference and business derivation.
7. Record rule/reasoning input graph sets, engine versions, generated statements, evidence/provenance
   dependencies, missing-evidence warnings, and audit status.

Acceptance criteria:

- OWL reasoning is available through backend API and result graphs.
- SHACL validation is the primary structural validation path.
- Business rule results are auditable and reviewable.
- Missing-evidence dependencies propagate to derived outputs.
- Rules and reasoning have clear execution boundaries.

## Phase 6: Graph-Derived Read APIs and Projections

Goal: make product reads and UI screens derive from semantic graph state rather than custom semantic
tables.

Tasks:

1. Evolve the Phase 0 direct SPARQL query endpoint toward policy-aware graph visibility.
2. Add JSON-LD documents for application consumption.
3. Add Turtle/TriG export for offline review and interoperability.
4. Keep compact business JSON projections for frontend screens and common agent tools.
5. Move Neo4j usage to visualization and high-speed traversal projections rebuilt from Oxigraph.
6. Move full-text and vector indexes toward rebuildable projections for labels, aliases, evidence,
   notes, and semantic retrieval.
7. Make query/display layers able to merge source graphs with current reasoning/rule result graphs
   without losing provenance.

Acceptance criteria:

- Key frontend screens can be backed by graph-derived business JSON.
- Standard semantic read interfaces are available.
- Neo4j-backed graph visualization reads from projection data only.
- Projection rebuild paths are documented and tested.

## Phase 7: Promote RDF Dataset Storage to Canonical

Goal: switch the canonical source of semantic truth from the current custom model to the RDF Dataset
and governed semantic services.

Tasks:

1. Migrate current semantic data from existing Postgres/Neo4j-backed structures into named graphs.
2. Verify parity between old model projections and RDF-derived projections.
3. Update structured product APIs so writes compile to RDF dataset changes.
4. Restrict Postgres to operational data where appropriate:
   users, jobs, credentials, service settings, run metadata, current result pointers, and other
   non-semantic workloads.
5. Treat Neo4j, search, and vector stores as rebuildable projections.
6. Remove or deprecate old semantic write paths after parity is proven.

Acceptance criteria:

- RDF Dataset/Oxigraph is the canonical semantic store.
- Product APIs and direct semantic APIs write to the same semantic representation.
- Old semantic storage is migrated, projection-only, or removed.
- Operational data remains in Postgres only where RDF is not the right workload.

## Phase 8: Frontend and Workflow Reshaping

Goal: align user-facing workflows with graph-native governance without forcing ordinary users to
write Turtle, TriG, JSON-LD, SPARQL, or OWL syntax.

Tasks:

1. Keep business-friendly screens for class creation, relation creation, assertion submission,
   validation, graph editability control, reasoning, rule execution, and knowledge recall.
2. Add expert/agent-facing semantic edit surfaces:
   TriG/JSON-LD input, constrained SPARQL Update, graph diff, SHACL validation, OWL reasoning
   result, evidence binding, audit status, and editability status.
3. Rework graph governance screens around named graphs, graph deltas, provenance, validation status,
   reasoning staleness, rule result staleness, and editability state.
4. Generate forms and allowed-property guidance from SHACL shapes.
5. Show whether a displayed statement is asserted, OWL-inferred, business-rule-derived, or missing
   evidence.

Acceptance criteria:

- Ordinary users still have product-level workflows.
- Expert tools and AI agents can submit precise semantic modeling statements.
- Reviewers and auditors can inspect graph-level changes, evidence/provenance, reasoning results,
  rule results, and staleness state.

## Immediate Implementation Order

1. Build the RDF-native service foundation from Phase 1.
2. Add semantic mapping/export from the current model in Phase 2.
3. Add governed query/edit paths from Phase 3.
4. Only promote RDF Dataset storage to canonical after export parity, validation, reasoning, edit,
   and projection behavior are proven.
