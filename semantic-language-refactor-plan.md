# Standard Semantic-Language Refactor Implementation Plan

## Source

- Governing ADR: `docs/adr/0004-semantic-web-first-refactor-target.md`
- Phase 0 foundation output: `docs/semantic/phase0-technical-foundation.md`
- ADR status: Proposed
- Planning date: 2026-07-04

## Current Progress

- Phase 0 technical route: decided and documented.
- Phase 1 design: completed in `docs/semantic/phase1-runtime-spine.md`.
- Implementation: Phase 1 runtime spine implemented and covered by backend tests.
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

## Phase 1: Semantic Runtime Spine and POC API

Goal: install the selected Phase 0 stack as a real backend boundary while keeping existing product
behavior unchanged.

Detailed checklist: `docs/semantic/phase1-runtime-spine.md`.

Confirmed scope decisions:

- Phase 1 is a sidecar semantic runtime POC. Existing product APIs remain backed by the current
  Postgres and Neo4j implementation.
- Oxigraph is added to the local Docker Compose startup path, while `OXIGRAPH_URL` can point to an
  external service.
- Postgres stores only operational semantic-runtime metadata: graph editability, validation runs,
  reasoning runs, and projection jobs.
- Phase 1 APIs live under `/api/semantic/...`.
- Governed semantic edits initially support Turtle, TriG, JSON-LD, `INSERT DATA`, and `DELETE DATA`.
  `DELETE/INSERT WHERE` is deferred to Phase 3.

Implementation focus:

1. Add backend configuration for:
   Oxigraph service URL, semantic base IRI, graph IRI prefixes, query timeout/result limits,
   pySHACL options, OWL reasoner command/service configuration, and Neo4j projection toggles.
2. Add an RDF store repository/service boundary over Oxigraph for:
   dataset load, named-graph read/write, SPARQL query, constrained SPARQL Update, graph export,
   and graph existence checks.
3. Add the seven Phase 0 POC endpoint categories:
   load/parse dataset, SPARQL query, SHACL validate, OWL reason, governed semantic edit,
   graph editability toggle, and TriG/JSON-LD export.
4. Store only operational semantic-runtime metadata in Postgres:
   graph editability state, validation-run records, reasoning-run records, current reasoning-result
   pointers, service settings, and projection job state.
5. Implement backend SHACL validation by fetching data and shape graphs from Oxigraph and running
   `pyshacl` or an equivalent local validation runtime.
6. Implement an OWL reasoner boundary with HermiT as the baseline candidate and Openllet as an
   evaluation candidate. Start with a command/service wrapper; do not mix reasoning into AI logic.
7. Add a minimal Neo4j projection proof sourced from Oxigraph source graphs plus the current
   reasoning-result graph when requested.
8. Add fixture datasets under backend tests for tiny TriG, Turtle, JSON-LD, SHACL, and OWL examples.

Acceptance criteria:

- A small TriG dataset can be loaded into Oxigraph, queried by named graph, and exported again.
- Caller-provided read SPARQL reaches Oxigraph through FastAPI with basic timeout/result controls.
- SHACL validation returns a report produced by the backend validation service, not by Oxigraph.
- OWL reasoning returns consistency/classification/entailment output and can persist a
  `graph:reasoning-result/{run_id}` graph without mutating source graphs.
- A locked graph rejects semantic edits without mutation.
- Neo4j can be populated from a small RDF graph projection and then rebuilt from RDF state.
- Backend tests cover the service boundary and POC API behavior with mocked or test-local services.

## Phase 2: Semantic Namespace, Mapping, and Export Baseline

Goal: define the platform's stable semantic language and prove the current model can be represented
in RDF/OWL/SKOS/SHACL before changing canonical writes.

Detailed implementation note: `docs/semantic/phase2-namespace-mapping-export.md`.

Implementation focus:

1. Document namespace and IRI conventions for projects, versions, ontology graphs, data graphs,
   classes, properties, relations, assertions, evidence, validation runs, reasoning runs, rule runs,
   policies, imports, reviews, and agents.
2. Add stable semantic IRIs to current domain objects without changing their existing persistence
   behavior yet.
3. Add JSON-LD contexts for platform resources, graph IDs, labels, aliases, evidence status,
   provenance, audit fields, editability, validation, reasoning, rules, and connector metadata.
4. Export current ontology schemas as RDF/OWL/SKOS:
   classes, labels, aliases, hierarchy, relation types, property domains/ranges, and controlled
   vocabularies.
5. Export current graph data, evidence links, provenance, fact claims, and missing-evidence status
   as RDF/PROV-O-compatible named graphs.
6. Generate SHACL shapes from current class, property, relation, and constraint definitions.
7. Add round-trip projection tests:
   current schema and facts -> RDF/OWL/SHACL -> compact business JSON projection.

Acceptance criteria:

- Current schemas export as Turtle, TriG, and JSON-LD with stable IRIs.
- Generated SHACL shapes express the current structural constraints used by product screens.
- Exported RDF preserves business-visible schema and data needed by existing screens.
- Missing-evidence facts are represented explicitly, not as verified facts.
- Round-trip tests prove that RDF export can reproduce the current business JSON projection.

## Phase 3: Governed Direct Semantic Interfaces

Goal: make direct semantic access first-class while preserving deterministic platform governance.

Implementation focus:

1. Promote the Phase 1 SPARQL endpoint into the agent-facing read interface over Oxigraph.
2. Implement semantic edit ingestion for Turtle, TriG, JSON-LD, and constrained SPARQL Update.
3. Keep SPARQL query and SPARQL Update separate:
   read SPARQL is a query path; update forms always go through governed semantic edit.
4. Start constrained SPARQL Update with delta-friendly forms:
   `INSERT DATA`, `DELETE DATA`, and restricted `DELETE/INSERT WHERE`.
5. Parse edits into graph deltas where practical, including target graph, inserted statements,
   removed statements, and affected source graphs.
6. Validate candidate post-edit graphs with SHACL and platform checks before commit.
7. Reject edits to locked actual graphs before applying mutations.
8. Record audit metadata:
   actor, time, reason, input format, target graph, validation result, graph delta, evidence
   status, and warning state.
9. Allow missing-evidence fact writes only when explicit evidence status and warning semantics are
   present.

Acceptance criteria:

- Agents can query complex graph state through SPARQL without chaining many fixed APIs.
- Agents and expert tools can submit direct semantic edits in standard formats.
- Invalid edits, locked-graph edits, and unsupported update forms do not mutate semantic data.
- Semantic edit audit records are queryable from Postgres metadata and/or RDF governance graphs.
- Missing-evidence facts produce warnings on write and read paths.

## Phase 4: Named-Graph Governance and Runtime State

Goal: make graph-native boundaries the platform governance model and remove draft/published
assumptions from the semantic refactor path.

Implementation focus:

1. Materialize canonical graph IRI categories:
   `graph:ontology/{graph_id}`, `graph:data/{graph_id}`, `graph:proposal/{proposal_id}`,
   `graph:evidence/{evidence_id}`, `graph:policy/{policy_id}`, `graph:import/{source_id}/{run_id}`,
   `graph:validation-run/{run_id}`, `graph:reasoning-run/{run_id}`,
   `graph:reasoning-result/{run_id}`, `graph:rule-run/{run_id}`,
   `graph:rule-result/{run_id}`, and `graph:review/{review_id}`.
2. Represent a working version as a graph set made of actual ontology/data graphs plus governance,
   evidence, validation, reasoning, rule, import, and policy graphs.
3. Replace any refactor-era draft/published promotion assumptions with per-actual-graph
   editability switches.
4. Store statement-level metadata using RDF-star/RDF 1.2 reification or named-graph metadata after
   checking what the selected Oxigraph version supports.
5. Keep OWL reasoning results in reasoning-result graphs, never in source ontology/data graphs.
6. Keep business rule results in rule-result graphs, never in source data graphs.
7. Add staleness detection for reasoning and rule results when source graphs, graph-set membership,
   engine versions, rule versions, or shape versions change.
8. Add garbage collection for superseded reasoning-result graphs after a newer successful run has
   become the current effective result.

Acceptance criteria:

- Actual ontology/data graphs can be locked and unlocked independently.
- Source assertions, OWL-inferred statements, and business-rule-derived statements remain
  distinguishable in storage and query output.
- Current effective reasoning result pointers are maintained in operational metadata.
- Superseded reasoning result graphs can be deleted without losing current query behavior.
- Audit/status reporting operates on graph deltas, editability state, validation state, and derived
  result staleness.

## Phase 5: Reasoning, Validation, and Deterministic Derivation

Goal: make semantic consistency, structural validation, and business derivation explicit,
separate platform services.

Implementation focus:

1. Use OWL reasoning for ontology consistency, class/property hierarchy classification,
   realization, and entailment checks over selected graph sets.
2. Use SHACL as the primary structural validation path for datatypes, cardinality, required
   properties, enum-like constraints, allowed relationships, and UI/form guidance.
3. Keep OWL reasoning, SHACL validation, SPARQL CONSTRUCT derivation, business rules, and workflow
   state machines as separate execution paths.
4. Support SPARQL CONSTRUCT for simple graph-derived assertions where it is sufficiently
   explainable.
5. Define a restricted Datalog-like or platform DSL for business rules that need stronger audit,
   review, incremental execution, or explanation than SPARQL CONSTRUCT provides.
6. Record rule/reasoning input graph sets, engine versions, generated statements,
   evidence/provenance dependencies, missing-evidence warnings, and audit status.
7. Propagate missing-evidence warnings from asserted inputs into rule-derived outputs.
8. Add explicit APIs and run records for validation, reasoning, and rule execution.

Acceptance criteria:

- OWL reasoning is available through backend APIs and persisted result graphs.
- SHACL validation reports are persisted and can be tied to graph sets and shape versions.
- Business rule results are auditable, reviewable, and stored separately from source graphs.
- Missing-evidence dependencies propagate to derived outputs and read surfaces.
- Tests prove that reasoning, validation, and business derivation do not silently mutate source
  graphs.

## Phase 6: Graph-Derived Product APIs and Projections

Goal: make product reads, UI screens, search, and traversal derive from RDF graph state rather than
custom semantic tables.

Implementation focus:

1. Add compact business JSON projections backed by SPARQL over source graphs plus current
   reasoning/rule result graphs where the view requires derived statements.
2. Add JSON-LD documents for application consumption and interop.
3. Add Turtle/TriG exports for offline review and standards-compatible tool inspection.
4. Move Neo4j usage to visualization and high-speed traversal projections rebuilt from Oxigraph.
5. Move full-text and vector indexes toward rebuildable projections for labels, aliases, evidence,
   notes, entity descriptions, and semantic retrieval.
6. Make projection rebuild jobs explicit and repeatable from Oxigraph graph sets.
7. Keep provenance, evidence status, assertion kind, and derived-result staleness visible in read
   models.
8. Start introducing policy-aware graph visibility after the core direct query/edit path is stable.

Acceptance criteria:

- Key frontend read screens can be backed by graph-derived business JSON.
- Standard semantic read interfaces are available: SPARQL, JSON-LD, Turtle, and TriG.
- Neo4j-backed graph visualization reads from projection data only.
- Search/vector/Neo4j projections can be dropped and rebuilt from Oxigraph state.
- Projection rebuild paths are documented and covered by tests or smoke checks.

## Phase 7: Canonical RDF Dataset Migration

Goal: switch semantic source-of-truth from the current custom model to Oxigraph RDF Dataset storage.

Implementation focus:

1. Migrate current semantic data from existing Postgres/Neo4j-backed structures into named graphs
   using the Phase 2 mapping.
2. Verify parity between old model projections and RDF-derived projections for schemas, entities,
   facts, evidence, validation state, reasoning state, and catalog/connector semantics where
   applicable.
3. Update structured product APIs so writes compile to governed RDF dataset changes.
4. Keep direct semantic APIs and structured product APIs writing the same canonical RDF
   representation.
5. Restrict Postgres to operational workloads where RDF is not the right storage model:
   users, sessions, credentials, jobs, service settings, connector settings, run metadata, current
   result pointers, and non-semantic records.
6. Treat Neo4j, search, vector stores, and frontend read caches as rebuildable projections.
7. Deprecate old semantic write paths after parity, validation, reasoning, edit, projection, and
   rollback behavior are proven.
8. Add migration rollback and re-run procedures for development and deployment environments.

Acceptance criteria:

- Oxigraph RDF Dataset is the canonical semantic store.
- Product APIs and direct semantic APIs write to the same governed semantic representation.
- Old semantic storage is migrated, projection-only, or removed.
- Operational data remains in Postgres only where RDF is not the right workload.
- Migration parity tests and projection rebuild tests pass before old write paths are disabled.

## Phase 8: Frontend and Workflow Reshaping

Goal: align user-facing workflows with graph-native governance without forcing ordinary users to
write Turtle, TriG, JSON-LD, SPARQL, or OWL syntax.

Implementation focus:

1. Keep business-friendly screens for class creation, relation creation, assertion submission,
   validation, graph editability control, reasoning, rule execution, import/export, and knowledge
   recall.
2. Add expert/agent-facing semantic edit surfaces:
   TriG/JSON-LD input, constrained SPARQL Update, graph diff, SHACL validation, OWL reasoning
   result, evidence binding, audit status, warning state, and editability state.
3. Rework graph governance screens around named graphs, graph sets, graph deltas, provenance,
   validation status, reasoning staleness, rule result staleness, and editability state.
4. Generate forms and allowed-property guidance from SHACL shapes where it improves ordinary-user
   workflows.
5. Show whether a displayed statement is asserted, OWL-inferred, business-rule-derived, imported,
   review metadata, policy metadata, or missing evidence.
6. Keep Protégé/WebProtégé outside platform core; provide standards-based import/export and
   inspection paths instead of embedding it in the product workflow.

Acceptance criteria:

- Ordinary users still have product-level workflows over the semantic graph.
- Expert tools and AI agents can submit precise semantic modeling statements.
- Reviewers and auditors can inspect graph-level changes, evidence/provenance, reasoning results,
  rule results, staleness state, and editability state.
- UI builds and smoke checks cover the reshaped workflows before the old screens are removed.

## Immediate Implementation Order

1. Build Phase 1 first: real Oxigraph/FastAPI/pySHACL/OWL-reasoner boundaries plus the seven POC
   endpoint categories.
2. Then complete Phase 2 mapping/export so existing platform objects have stable IRIs,
   JSON-LD contexts, SHACL shape generation, and round-trip projection tests.
3. Then harden Phase 3 governed semantic query/edit, especially constrained SPARQL Update, graph
   delta handling, editability checks, audit metadata, and missing-evidence warnings.
4. Then implement graph-native governance in Phase 4 before attempting canonical migration.
5. Only promote RDF Dataset storage to canonical in Phase 7 after export parity, validation,
   reasoning, semantic edit, projection rebuild, and rollback behavior are proven.

## Verification Policy

- Backend behavior changes must include tests under `backend/tests/` and be verified with
  `cd backend && uv run pytest`.
- Frontend workflow changes must be verified with `cd frontend && npm run build` and
  `cd frontend && npx playwright test`.
- Documentation-only updates to this plan do not require backend or frontend test execution.
