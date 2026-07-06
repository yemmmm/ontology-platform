# Standard Semantic-Language Refactor Integration Test Plan

## Purpose

This plan verifies the integrated behavior of the standard semantic-language refactor after the
phase implementation work described in `semantic-language-refactor-plan.md`.

The emphasis is cross-phase behavior, not isolated service unit coverage. Tests should prove that
RDF Dataset storage, named-graph governance, direct semantic editing, SHACL validation, OWL
reasoning, deterministic rule derivation, graph-derived read models, projections, canonical RDF
migration, and the reshaped frontend workflow operate as one governed platform path.

## Scope

In scope:

- Semantic runtime endpoints under `/api/semantic/*`.
- Import/export endpoints that expose namespace manifests, RDF/OWL/SKOS exports, generated SHACL,
  and compact projection parsing.
- MCP semantic tools that wrap the same service paths.
- Frontend governance workspaces introduced in Phase 8.
- PostgreSQL operational metadata for graph registry, graph sets, run records, derived pointers,
  projection jobs, migration runs, edit audit, and canonical mode.
- Oxigraph RDF Dataset behavior through the repository boundary.
- Neo4j, search, and vector projection rebuild behavior as rebuildable outputs.

Out of scope:

- Benchmarking large RDF datasets.
- Full authorization/RBAC policy validation beyond the current light visibility policy.
- Real HermiT/Openllet performance and completeness validation. Integration may use a configured
  fake or test command runner unless a dedicated reasoner environment is available.
- Protégé/WebProtégé integration.

## Test Environment

Run the suite against the local stack started by:

```bash
./scripts/start-local.sh
```

Minimum services:

- FastAPI backend.
- PostgreSQL with all Alembic migrations applied.
- Oxigraph service reachable through `OXIGRAPH_URL`.
- Neo4j reachable when projection rebuild tests are enabled.
- Frontend dev or preview server for Playwright checks.

Recommended validation commands:

```bash
cd backend && uv run pytest
cd frontend && npm run build
cd frontend && npx playwright test
```

For a narrower semantic integration pass while iterating:

```bash
cd backend && uv run pytest tests/test_semantic_api.py tests/test_semantic_phase5.py tests/test_semantic_phase6_api.py tests/test_semantic_phase7_api.py
cd frontend && npx playwright test frontend/tests/semantic-governance.spec.ts
```

## Shared Seed Dataset

Use one deterministic test project, ontology, version, and graph set:

- Project: `semantic-it-project`.
- Ontology: `semantic-it-ontology`.
- Version/scope: `semantic-it-version`.
- Ontology graph: `graph:ontology/semantic-it`.
- Data graph: `graph:data/semantic-it`.
- Shape graph: `graph:shapes/semantic-it`.
- Evidence graph: `graph:evidence/semantic-it`.
- Policy graph: `graph:policy/semantic-it`.
- Graph set: `semantic-it-graph-set`, containing ontology, data, shape, evidence, and policy graphs.

The RDF fixture should contain:

- Two classes: `Person`, `Organization`.
- Datatype properties: `name`, `age`, `externalId`.
- Object property/relation: `worksFor`.
- At least two entities, one valid and one intentionally invalid for SHACL.
- One fact with explicit verified evidence.
- One fact with explicit `missing_evidence` status and warning metadata.
- One rule input that derives a new assertion from the missing-evidence fact.
- One OWL axiom that produces a small, deterministic inferred statement through the fake/test
  reasoner.

Fixture formats required:

- TriG dataset for named-graph load/export.
- Turtle graph content for single graph edit/export.
- JSON-LD payload with the platform context.
- SHACL shapes for required property, datatype, and relation target constraints.
- A compact business JSON expectation for round-trip parity.

## Integration Scenarios

### 1. Runtime Spine and RDF Dataset Boundary

Goal: prove FastAPI orchestrates Oxigraph-backed semantic state without changing legacy product API
behavior accidentally.

Steps:

1. Load the shared TriG dataset through `POST /api/semantic/datasets:load`.
2. Query each named graph through `POST /api/semantic/sparql:query`.
3. Export the dataset through `/api/semantic/export` or graph-set export as TriG and JSON-LD.
4. Verify legacy product endpoints still respond for the same project/ontology.

Assertions:

- Named graph IRIs are preserved.
- Read SPARQL rejects write operations and points callers to governed edits.
- Exported TriG parses back into the expected graph count and key triples.
- Runtime failures from Oxigraph map to deterministic HTTP errors.

### 2. Namespace Mapping, RDF Export, and Round Trip

Goal: prove current business-facing schemas and facts can be represented in standard semantic
formats and projected back.

Steps:

1. Create project, ontology, classes, properties, relation types, entities, evidence, and fact
   claims through existing product APIs.
2. Call `/api/semantic/namespaces`.
3. Export schema/data through semantic export endpoints in Turtle, TriG, and JSON-LD.
4. Export generated SHACL shapes.
5. Parse the semantic export through `POST /api/semantic/projections:parse`.

Assertions:

- Stable IRIs are generated for project, ontology, version, classes, properties, entities,
  assertions, evidence, catalog objects, and governance records.
- OWL/SKOS/RDFS semantics preserve labels, aliases, hierarchy, domains, ranges, and controlled
  values.
- SHACL captures product-visible required, cardinality, datatype, enum-like, and relation target
  constraints.
- Missing-evidence facts remain explicit and are not projected as verified facts.
- Compact projection matches the expected business JSON fields.

### 3. Governed Direct Semantic Edit Path

Goal: prove AI/expert direct modeling statements use the same deterministic governance path as
structured writes.

Steps:

1. Submit Turtle into an editable target graph through `POST /api/semantic/edits`.
2. Submit TriG with explicit graph boundaries.
3. Submit JSON-LD with the platform context.
4. Submit constrained `INSERT DATA` and `DELETE DATA`.
5. Submit unsupported SPARQL Update and malformed RDF.
6. Lock the data graph through `PATCH /api/semantic/graphs/{graph_iri}/editability` and retry a
   valid edit.

Assertions:

- Successful edits return graph deltas, validation status, audit metadata, warning state, and stale
  derived pointers when applicable.
- Locked-graph, unsupported-update, and invalid-RDF requests do not mutate Oxigraph or graph
  revision metadata.
- Missing-evidence writes require explicit evidence status and warning state.
- Edit audit is visible through `GET /api/semantic/edits/audits`.

### 4. Named-Graph Governance and Graph Sets

Goal: prove graph-native governance is the runtime boundary.

Steps:

1. Register ontology, data, shape, evidence, validation-run, reasoning-result, rule-result, import,
   policy, and review graphs.
2. Create a graph set with actual source graphs and governance graphs.
3. Change graph-set membership.
4. Reconcile derived result pointers.
5. Run garbage collection for superseded derived result graphs.

Assertions:

- Actual ontology/data graphs can be locked independently.
- Governance and result graphs are protected from ordinary direct edits.
- Graph-set source signatures change when members or source revisions change.
- Reasoning and rule pointers become stale after relevant source graph or membership changes.
- GC only deletes eligible superseded derived result graphs and never deletes current/source graphs.
- Governance status reports graph counts, editability counts, stale derived counts, validation
  summary, projection status, and warning counts.

### 5. SHACL Validation, OWL Reasoning, and Rule Derivation

Goal: prove validation, reasoning, and deterministic derivation are separate, auditable execution
paths.

Steps:

1. Run graph-set SHACL validation through
   `POST /api/semantic/graph-sets/{graph_set_id}/validation-runs`.
2. Inspect `GET /api/semantic/validation-runs/{run_id}`.
3. Run graph-set reasoning through
   `POST /api/semantic/graph-sets/{graph_set_id}/reasoning-runs`.
4. Create a SPARQL CONSTRUCT rule definition and a platform DSL rule definition.
5. Run each rule through `POST /api/semantic/graph-sets/{graph_set_id}/rule-runs`.
6. Inspect missing-evidence dependencies through the graph-set missing-evidence endpoint.

Assertions:

- SHACL reports are persisted with graph set, shape graph/version, engine metadata, conforms flag,
  violation count, and optional form guidance.
- Reasoning writes only to `graph:reasoning-result/{run_id}` and promotes a reasoning pointer when
  requested.
- Rule execution writes only to `graph:rule-result/{run_id}` and promotes a rule pointer when
  requested.
- Source ontology/data graphs are unchanged by validation, reasoning, and rule runs.
- Missing-evidence warnings propagate to derived outputs and read surfaces.
- SPARQL CONSTRUCT remains constrained to approved deterministic templates; unrestricted write
  behavior is rejected.

### 6. Graph-Derived Read Models and Standard Exports

Goal: prove product reads can be derived from RDF graph sets with provenance and staleness metadata.

Steps:

1. Query graph-derived read models such as ontology schema summary, entities, statements, resources,
   and compact business JSON.
2. Request asserted-only views and views including current reasoning/rule results.
3. Export graph sets as TriG, Turtle where valid, JSON-LD, and compact business JSON.
4. Exercise light visibility policy labels and redaction behavior.

Assertions:

- Read-model envelopes include graph set id, source signature, included assertion kinds,
  provenance, evidence status, assertion kind, source graph IRI, and stale warnings.
- Derived result inclusion uses current pointers rather than hard-coded graph IRIs.
- Turtle export rejects multi-graph graph sets unless narrowed to one graph.
- JSON-LD context is stable and parseable.
- Visibility labels and redaction do not leak hidden graph content.

### 7. Projection Rebuilds

Goal: prove Neo4j, search, vector, and UI-facing projections are rebuildable outputs rather than
canonical stores.

Steps:

1. Create projection jobs for Neo4j, search, and vector targets.
2. Run the projection jobs.
3. Drop or clear the target projection partition.
4. Re-run the same jobs from the same graph set and current derived pointers.
5. Change a source graph and reconcile projection freshness.

Assertions:

- Projection manifests record graph set, source signature, source graph revisions, current derived
  pointers, projection kind, projection version, target partition, and job status.
- Rebuilds are idempotent for the same source signature.
- Projection status becomes stale when semantic source state or projection version changes.
- Neo4j visualization data is read from projection metadata and can be rebuilt from RDF state.
- Search/vector documents carry source signature, projection version, evidence/provenance, and
  warning metadata.

### 8. Canonical RDF Dataset Migration and Product Write Convergence

Goal: prove Phase 7 source-of-truth migration controls are safe before legacy semantic writes are
disabled.

Steps:

1. Run `POST /api/semantic/migrations:preflight` for the shared ontology/version scope.
2. Create dry-run, shadow, dual-write, and cutover migration runs.
3. Run batches and parity checks.
4. Apply a structured product command through `/api/semantic/canonical-writes:*`.
5. Apply an equivalent direct semantic edit.
6. Cut over only after gates pass.
7. Roll back and verify canonical mode returns to the expected state.
8. Rerun failed batches to verify idempotence.

Assertions:

- Preflight reports inventory, unsupported items, readiness, warnings, and expected graph targets.
- Dry run does not mutate Oxigraph.
- Shadow mode writes expected named graphs and graph registry entries without switching reads.
- Dual-write compare reports parity for schema, classes, properties, relation types, entities, fact
  claims, evidence, validation state, derived pointers, catalog, connector, identifier resolution,
  product API reads, SPARQL/direct reads, Neo4j visualization, search/vector, and export/import.
- Cutover is blocked when validation, parity, projection rebuild, or rollback gates fail.
- Product commands and direct semantic edits converge on the same graph delta, validation,
  editability, audit, revision, staleness, and projection invalidation pipeline.
- Rollback restores legacy mode and leaves enough RDF export/audit evidence for diagnosis.
- Legacy write blocking returns deterministic errors only after the configured gate is enabled.

### 9. MCP Semantic Tools

Goal: prove agent-facing MCP tools exercise the same governed services as HTTP.

Steps:

1. Run semantic SPARQL query, semantic edit, graph-set status, validation, reasoning, rule run,
   missing-evidence inspection, read-model export, projection status, migration preflight, batch,
   cutover, and rollback through MCP tools.
2. Compare HTTP and MCP response shapes for the same seeded graph set.

Assertions:

- MCP tools do not expose bypass paths for write SPARQL, unrestricted CONSTRUCT execution, or
  locked graph mutation.
- Tool responses include the same run ids, graph deltas, warnings, stale pointers, and projection
  status as HTTP.

### 10. Frontend Governance Workflow Smoke

Goal: prove Phase 8 surfaces the new governance model without requiring ordinary users to author
raw semantic syntax.

Steps:

1. Open the Governance stage tabs:
   `graph-governance`, `named-graphs`, `graph-sets`, `semantic-edits`, `semantic-runs`,
   `semantic-import-export`.
2. Verify named graph registry, graph set detail, current derived pointers, staleness badges, and
   projection status.
3. Preview a TriG or JSON-LD semantic edit and inspect graph delta/validation warnings before apply.
4. Run or inspect validation, reasoning, and rule runs.
5. Load/export semantic content and run a read SPARQL query.
6. Verify Chinese translations for new visible labels.

Assertions:

- Existing Modeling workflows remain reachable.
- Ordinary user workflows expose graph target, editability, SHACL guidance, evidence/provenance,
  assertion kind, and warning state without forcing raw RDF syntax.
- Expert/agent surfaces make TriG, Turtle, JSON-LD, and constrained SPARQL Update available only
  through governed edit paths.
- UI build and Playwright smoke pass without layout regressions in governance screens.

## Failure and Safety Matrix

| Failure | Expected behavior |
| --- | --- |
| Oxigraph unavailable | Semantic endpoints return deterministic dependency errors; product APIs not using semantic runtime keep working. |
| Read SPARQL contains write operation | Request is rejected and no mutation occurs. |
| Unsupported SPARQL Update | Request is rejected before mutation. |
| Locked actual graph edit | Request is rejected and graph revision is unchanged. |
| Governance/result graph direct edit | Request is rejected unless invoked by an allowed platform workflow. |
| SHACL violation | Candidate edit or migration gate is blocked unless an explicit policy allows warning-only behavior. |
| Reasoner command unavailable | Reasoning run records a dependency/configuration failure without mutating source graphs. |
| Rule execution error | Rule run fails without writing source graphs or promoting current rule pointer. |
| Missing evidence omitted | Write is rejected when missing-evidence semantics are required. |
| Projection rebuild failure | Canonical mode and UI cutover stay unchanged; projection job records failure and retry metadata. |
| Parity drift | Cutover is blocked and parity report identifies affected scope/items. |
| Rollback requested after cutover | Mode switches back according to rollback policy and projections are rebuilt from the rollback source. |

## Stage 1: Intake Refactor Smoke Entries

### Build Overview -- graph-set read model

| Endpoint | Expected | Notes |
| --- | --- | --- |
| `GET /ontologies/{id}/build-overview?project_id={pid}` | 200 with expected fields | Returns `ontology`, `brief`, `questions`, `staleness` keys |
| `GET /ontologies/{id}/build-overview` (no active graph-set) | 404 | Ontology without a graph-set gets a deterministic 404 |
| `GET /graph-sets/{gs}/read-models/graph-set-staleness` | 200 envelope | `SemanticReadModelEnvelope` shape even when graphs are empty |
| `GET /projects/{id}/build-context` (legacy) | `Deprecation: true` header present | Sunset header also present |

### Competency Question validate -- SPARQL dispatch

| Endpoint | Expected | Notes |
| --- | --- | --- |
| `POST /competency-questions/{id}/validate` with entity_count question | 200 | Runs SPARQL COUNT query against active graph-set |
| Same with relation_count question | 200 | Runs SPARQL COUNT query against active graph-set |
| Same with sparql_count question | 200 | Runs SPARQL SELECT COUNT against active graph-set |
| Same with CONSTRUCT query body | 422 | CONSTRUCT is rejected as a read-only competency question |
| Same with INSERT query body | 422 | INSERT is rejected as a read-only competency question |

## Stage 2: Modeling / Knowledge Rebuild Smoke Entries

### FactAuditPage — fact-audit-queue read model by kind

| Endpoint | Expected | Notes |
| --- | --- | --- |
| `GET /graph-sets/{gs}/read-models/fact-audit-queue?kind=asserted` | 200 envelope | Items carry `assertion_kind: "asserted"`, sourced from asserted_data members |
| `GET /graph-sets/{gs}/read-models/fact-audit-queue?kind=inferred` | 200 envelope | Items sourced from effective reasoning-result graph; rows carry `derived_from.run_id` |
| `GET /graph-sets/{gs}/read-models/fact-audit-queue?kind=rule_derived` | 200 envelope | Items sourced from effective rule-result graph |
| `GET /graph-sets/{gs}/read-models/fact-audit-queue?kind=missing_evidence` | 200 envelope | Items filtered to subjects with `op:evidenceStatus "missing_evidence"` |
| `GET /graph-sets/{gs}/read-models/fact-audit-queue?kind=inferred` (no reasoning pointer) | 200 envelope, empty items, warning `fact_audit_no_inferred_pointer` | Frontend renders "click Generate to run reasoning" empty state |
| `GET /graph-sets/{gs}/read-models/fact-audit-queue?kind=not_a_kind` | 400 | ReadModelError surfaces invalid kind value |
| `GET /graph-sets/{gs}/read-models/missing-evidence-list` | 200 envelope | Lightweight aggregator across asserted_data members |

### FactAuditPage — review_assertion canonical-write

| Endpoint | Expected | Notes |
| --- | --- | --- |
| `POST /canonical-writes:compile-and-apply` kind=review_assertion, assertion_kind=asserted | 200, delta applied to `graph/data/{ontology_id}` | Writes RDF-star reification `<<s p o>> op:auditStatus "approved"` etc. |
| Same with assertion_kind=inferred + result_graph_iri | 200, delta applied to reasoning-result graph | Compiler validates that result_graph_iri is supplied |
| Same with decision=rejected, missing linked_fix_proposal_id | 400 | Compiler rejects with InvalidCommandPayload |
| Same with decision=maybe | 400 | decision must be approved / rejected / needs_correction |
| Returned metadata.fact_id | 64-char hex digest | SHA-256 over canonical N-Triples form of (subject, predicate, object) |

### FactAuditPage — Generate / Run rules / Recall

| Endpoint | Expected | Notes |
| --- | --- | --- |
| `POST /graph-sets/{gs}/reasoning-runs` triggered by Generate | 202, run_id returned | Frontend polls until status=succeeded |
| `POST /graph-sets/{gs}/rule-runs` triggered by Generate / Run rules | 202, run_id returned | Frontend polls until status=succeeded |
| `GET /reasoning-runs/{run_id}` polling | eventually status=succeeded | Reasoning result graph becomes effective pointer |
| `GET /rule-runs/{run_id}` polling | eventually status=succeeded | Rule result graph becomes effective pointer |
| `POST /sparql:query` (Recall) | 200, bindings returned as asserted rows | Frontend renders rows in the fact queue with assertion_kind=asserted |

## Acceptance Gates

The refactor is integration-ready when:

1. Backend semantic API tests pass with the local database and semantic test doubles or local
   Oxigraph where configured.
2. At least one live Oxigraph-backed test loads, queries, edits, validates, and exports a named
   graph dataset.
3. Graph set validation, reasoning, rule derivation, stale pointer reconciliation, and derived GC
   are tested in one ordered scenario.
4. Graph-derived read models and exports are parity-checked against compact expected business JSON.
5. Projection jobs can be created, run, marked stale, and rerun.
6. Migration preflight, dry-run, shadow, dual-write parity, cutover block/pass, rollback, and rerun
   behavior are covered.
7. Frontend build and semantic governance Playwright smoke pass.
8. No test depends on direct mutation of Neo4j/search/vector as semantic source of truth.

## Suggested Test File Layout

- `backend/tests/integration/test_semantic_runtime_flow.py`
- `backend/tests/integration/test_semantic_governance_flow.py`
- `backend/tests/integration/test_semantic_derivation_flow.py`
- `backend/tests/integration/test_semantic_projection_flow.py`
- `backend/tests/integration/test_semantic_migration_flow.py`
- `backend/tests/integration/test_semantic_mcp_flow.py`
- `frontend/tests/semantic-governance.spec.ts` for UI smoke, extended with live-contract fixtures
  where practical.

Keep existing unit/API tests in place. The integration tests should reuse shared fixtures and verify
ordered cross-service behavior that cannot be proven by isolated tests.
