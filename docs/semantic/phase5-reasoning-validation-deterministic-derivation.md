# Phase 5 Reasoning, Validation, and Deterministic Derivation

> **Note (2026-07-08):** The missing-evidence propagation described in this
> document previously relied on the RDF-side `op:evidenceStatus` literal
> (`"missing_evidence"` / `"derived_from_missing_evidence"`) and the
> `missing_evidence_dependencies` derivation metadata. Those RDF markers
> have been removed; "missing evidence" is now a derived state computed
> from the Postgres `fact_evidence_bindings` table (a fact with zero
> bindings is missing). See
> `docs/superpowers/specs/2026-07-08-evidence-postgres-refactor-design.md`.

## Status

Detailed design. Phase 5 builds on the Phase 1 semantic runtime spine, the Phase 2 namespace and
export baseline, the Phase 3 governed edit path, and the Phase 4 graph registry, graph sets,
derived-result pointers, and staleness model.

Phase 5 does not migrate product APIs to canonical RDF storage. It makes reasoning, validation,
SPARQL CONSTRUCT derivation, business-rule execution, missing-evidence propagation, and workflow
state derivation explicit platform services over named graph sets.

## Goal

Make semantic consistency, structural validation, and deterministic business derivation separate,
auditable execution paths.

The platform should be able to run OWL reasoning, SHACL validation, simple SPARQL CONSTRUCT
derivation, restricted business rules, and workflow state transitions without silently mutating
source ontology or data graphs. Derived statements must be written to result graphs and described
by run metadata, provenance, evidence dependencies, warnings, and current/stale pointers.

## Confirmed Decisions

1. OWL reasoning remains the path for ontology consistency, classification, realization, and
   entailment checks.
2. SHACL remains the primary structural validation path for datatypes, cardinality, required
   properties, enum-like constraints, allowed relationships, and UI/form guidance.
3. SPARQL CONSTRUCT is allowed only for simple, explainable graph-derived assertions.
4. Business rules that require review, audit, incremental execution, stable explanations, or
   missing-evidence propagation use a restricted platform DSL instead of unrestricted SPARQL.
5. Workflow state transitions are a separate execution mode. They may be driven by rule results,
   but they are not OWL entailments or SHACL validation failures.
6. Source ontology/data graphs are never mutated by reasoning, validation, CONSTRUCT derivation,
   business rules, or workflow-state execution.
7. Reasoning results are written to `graph/reasoning-result/{run_id}` graphs.
8. Rule and CONSTRUCT results are written to `graph/rule-result/{run_id}` graphs.
9. Validation reports are written to `graph/validation-run/{run_id}` graphs when persisted as RDF,
   and summarized in `semantic_validation_runs`.
10. Missing-evidence warnings from asserted inputs must propagate to derived outputs and read
    surfaces.

## Non-Goals

- Do not adopt SWRL as the default rule runtime.
- Do not add a general-purpose programming language as a rule body.
- Do not let rule execution write derived facts back into source ontology/data graphs.
- Do not make Oxigraph responsible for SHACL validation or OWL reasoning.
- Do not implement full role-based access control or graph visibility policy.
- Do not require incremental rule execution in the first Phase 5 pass.
- Do not migrate the existing legacy `rule_definitions` product table into canonical RDF writes in
  this phase. It may be adapted for compatibility, but Phase 5 semantic rule execution must have
  its own graph-set-aware run records.

## Execution Boundaries

Phase 5 keeps each semantic execution path independent:

| Path | Input | Output | Result graph | Pointer kind |
| --- | --- | --- | --- | --- |
| OWL reasoning | asserted ontology/data/import graphs, selected tasks | consistency, classification, realization, entailments | `graph/reasoning-result/{run_id}` | `reasoning` |
| SHACL validation | data graphs plus shape graphs | conforms flag, SHACL report, UI guidance | `graph/validation-run/{run_id}` | none in Phase 4, optional `validation` later |
| SPARQL CONSTRUCT derivation | graph set plus one approved CONSTRUCT template | generated triples/quads and explanation bindings | `graph/rule-result/{run_id}` | `rule` |
| Platform DSL rules | graph set plus compatible rule definitions | generated statements, warnings, explanation records | `graph/rule-result/{run_id}` | `rule` |
| Workflow state machine | graph set plus workflow definition/version | state-transition events or validation outputs | `graph/rule-result/{run_id}` or workflow operational tables | `rule` when graph-derived |

The shared contract is:

```text
resolve graph set
  -> snapshot input graph revisions and current derived pointers
  -> run one execution path
  -> validate and classify generated statements
  -> write run metadata graph
  -> write result graph when statements are produced
  -> persist operational run record
  -> update current derived pointer when the run is promoted
  -> mark dependent projections or later derived results stale
```

## Graph Inputs and Outputs

Graph-set roles from Phase 4 are reused without redefining version semantics.

Reasoning input roles:

- `asserted_ontology`
- `asserted_data` when realization or data entailment is requested
- `import`
- optional `shape` only when a reasoner profile explicitly needs shape/version context

Validation input roles:

- `asserted_data`
- `shape`
- optional `asserted_ontology` for class/property context
- optional current `reasoning_result` when validation is explicitly configured to validate the
  working view rather than asserted data only

Rule and CONSTRUCT input roles:

- `asserted_ontology`
- `asserted_data`
- current `reasoning_result` only when the rule declares `uses_inferred_facts=true`
- current `rule_result` only for explicitly ordered dependent rule groups
- `evidence`
- `policy`
- `import`

Outputs:

- Reasoning writes only to `reasoning-run` and `reasoning-result` graphs.
- Validation writes only to `validation-run` graphs and `semantic_validation_runs`.
- CONSTRUCT and DSL rules write only to `rule-run` and `rule-result` graphs.
- Workflow graph outputs, when represented as semantic statements, use `rule-run` and
  `rule-result` graphs with `op:assertionKind "workflow_derived"`.

## Run Metadata

Every run must record enough information to reproduce or explain the result.

Common run metadata:

| Field | Meaning |
| --- | --- |
| `graph_set_id` | Graph set used by the run. |
| `source_signature` | Phase 4 graph-set source signature consumed by the run. |
| `input_graph_revisions` | Graph IRI to revision map at execution time. |
| `input_derived_pointers` | Current reasoning/rule pointers consumed by the run. |
| `engine_name` | Reasoner, SHACL engine, CONSTRUCT executor, or DSL engine name. |
| `engine_version` | Runtime version or command signature. |
| `definition_version` | Shape version, rule version, workflow version, or template version. |
| `started_at` / `finished_at` | Execution timing. |
| `status` | `pending`, `running`, `succeeded`, `failed`, or `promoted`. |
| `generated_statement_count` | Number of statements persisted to a result graph. |
| `evidence_dependencies` | Evidence resources and status values used by the run. |
| `missing_evidence_dependencies` | Inputs that were explicitly missing evidence. |
| `warnings` | Non-fatal warnings surfaced to callers and read models. |
| `audit_status` | `system_accepted`, `pending_review`, `rejected`, or `superseded`. |

Operational records stay in Postgres. Semantic run metadata can also be mirrored into the
corresponding run graph using PROV-O and the platform vocabulary.

## Postgres Metadata Design

Phase 5 extends the existing Phase 1 and Phase 4 operational tables instead of storing RDF
statements in Postgres.

### Extend `semantic_validation_runs`

Add or populate these metadata keys in `semantic_validation_runs.metadata`:

| Key | Meaning |
| --- | --- |
| `graph_set_id` | Optional graph set when validation is graph-set-aware. |
| `source_signature` | Source signature consumed by the run. |
| `input_graph_revisions` | Revisions of data and shape graphs. |
| `shape_version` | Deterministic shape bundle/version identifier. |
| `engine_name` | Usually `pyshacl`. |
| `engine_version` | pySHACL and rdflib version details. |
| `validation_scope` | `asserted_only`, `asserted_plus_reasoning`, or custom scope. |
| `guidance` | Optional UI/form guidance derived from shapes. |

`report_graph_iri` points to `graph/validation-run/{run_id}` when the SHACL report is persisted as
RDF.

### Extend `semantic_reasoning_runs`

Add or populate these metadata keys in `semantic_reasoning_runs.metadata`:

| Key | Meaning |
| --- | --- |
| `graph_set_id` | Graph set used by graph-set-aware reasoning. |
| `source_signature` | Source signature consumed by the run. |
| `input_graph_revisions` | Revisions of ontology/data/import graphs. |
| `tasks` | Requested tasks such as `consistency`, `classification`, `realization`, `entailment`. |
| `profile` | `owl2_dl` by default; other profiles require explicit opt-in. |
| `engine_version` | Reasoner implementation version or command signature. |
| `shape_version` | Optional shape context version if used. |
| `warnings` | Non-fatal reasoner warnings. |

Successful persisted reasoning runs continue to promote `semantic_derived_result_pointers` with
`result_kind="reasoning"`.

### Add `semantic_rule_definitions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `rule_iri` | text | Stable semantic IRI for the rule definition. |
| `name` | string | Human-readable name. |
| `language` | string | `sparql_construct`, `platform_dsl`, or `workflow_state_machine`. |
| `version` | string | Immutable version identifier for the rule body. |
| `status` | string | Compatibility field; stored rules are normalized to `active` and are immediately executable. |
| `body` | JSONB/text | Rule body or CONSTRUCT template. |
| `input_roles` | JSONB | Allowed graph-set roles the rule may read. |
| `output_kind` | string | `assertion`, `validation`, `workflow`, or `annotation`. |
| `uses_inferred_facts` | bool | Whether the current reasoning-result pointer is an input dependency. |
| `requires_review` | bool | Whether generated statements start as `pending_review`. |
| `safety_profile` | JSONB | Limits such as max results, allowed predicates, and timeout. |
| `created_by` | string nullable | Actor or service creating the rule. |
| `created_at` / `updated_at` | timestamptz | Runtime bookkeeping. |
| `metadata` | JSONB | Labels, owners, explanation template, or migration notes. |

Rule definitions are operational control records. A semantic representation of each stored rule may
also be exported to a policy or rule metadata graph, but the executable source in Phase 5 is this
versioned operational record.

### Add `semantic_rule_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key and run id. |
| `graph_set_id` | string FK | Graph set used by the run. |
| `rule_definition_id` | string nullable | Null when the run executes a batch or workflow group. |
| `rule_version` | string nullable | Version executed. |
| `result_graph_iri` | text | `graph/rule-result/{run_id}` when statements are persisted. |
| `rule_run_graph_iri` | text nullable | `graph/rule-run/{run_id}` metadata graph. |
| `engine_name` | string | `sparql_construct`, `platform_dsl`, or workflow engine name. |
| `engine_version` | string nullable | Engine version or code signature. |
| `source_signature` | string | Graph-set source signature consumed by the run. |
| `status` | string | `pending`, `running`, `succeeded`, `failed`, or `promoted`. |
| `generated_statement_count` | int | Count written to result graph. |
| `started_at` / `finished_at` | timestamptz | Runtime bookkeeping. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Dependencies, warnings, explanations, audit status, and review summary. |

A successful rule run may promote a Phase 4 derived-result pointer with `result_kind="rule"`.

## Rule Language Design

### SPARQL CONSTRUCT Profile

SPARQL CONSTRUCT is allowed for simple deterministic derivations.

Allowed:

- `CONSTRUCT { ... } WHERE { ... }`
- `PREFIX`
- `VALUES`
- `FILTER` over deterministic scalar comparisons
- explicit `GRAPH <iri> { ... }` patterns limited to graph-set member IRIs
- named variables that can be captured in explanation bindings

Rejected:

- `SERVICE`
- update forms
- property paths without an explicit max-depth policy
- arbitrary graph writes
- unbounded result sets
- dynamic graph IRIs outside the graph set
- non-deterministic functions for generated identifiers

The executor must apply a timeout, result limit, and generated-statement limit before writing the
result graph.

### Platform DSL Profile

The DSL is intentionally small and Datalog-like. It should support:

- named rule id and immutable version
- declared input graph roles
- typed variables
- triple patterns
- equality and scalar comparisons
- joins over matched variables
- optional existence checks
- deterministic output templates
- evidence dependency propagation
- explanation templates

Conceptual shape:

```json
{
  "when": [
    {"s": "?student", "p": "rdf:type", "o": "ex:Student"},
    {"s": "?student", "p": "ex:averageScore", "o": "?score"},
    {"filter": {"gte": ["?score", 90]}}
  ],
  "then": [
    {"s": "?student", "p": "rdf:type", "o": "ex:ExcellentStudent"}
  ],
  "explain": "Student average score is at least 90"
}
```

The first implementation may compile this DSL to parameterized SPARQL SELECT plus deterministic
statement templates. It must not accept arbitrary Python or JavaScript.

## Missing-Evidence Propagation

Missing evidence is a first-class dependency, not a warning string added at the end.

Propagation rules:

1. Any asserted input statement with `op:evidenceStatus "missing_evidence"` adds a missing-evidence
   dependency to the run.
2. Any generated statement that depends on that input receives a statement annotation in the
   rule-result graph or an associated metadata graph.
3. The generated statement uses `op:evidenceStatus "derived_from_missing_evidence"` unless a
   stricter status is configured.
4. The run metadata records `missing_evidence_dependencies` with input statement identifiers,
   graph IRIs, and matched bindings where available.
5. Read models that include the result graph must surface the warning and should identify whether
   the statement is asserted, OWL-inferred, rule-derived, or workflow-derived.

Reasoning results may not always preserve a one-to-one proof dependency from the reasoner. When
proof dependencies are unavailable, the reasoning run should record a conservative warning if any
input graph contains missing-evidence assertions and the task includes data realization or
entailment over those assertions.

## Validation Flow

Graph-set-aware validation:

```text
receive validation request
  -> resolve graph set
  -> collect data and shape graph members
  -> snapshot revisions and shape version
  -> fetch RDF graphs through RdfStoreRepository
  -> run pySHACL in backend validation service
  -> persist semantic_validation_runs
  -> optionally write graph/validation-run/{run_id}
  -> mark report stale when data or shape revisions change
```

Validation reports are not promoted as rule or reasoning pointers in the first Phase 5 pass. They
are run records tied to graph-set signatures and shape versions. Phase 4's unfinished validation
staleness item should be completed here.

## Reasoning Flow

Graph-set-aware reasoning extends the Phase 4 endpoint:

```text
receive reasoning request
  -> resolve graph set and task profile
  -> collect asserted ontology/data/import graph members
  -> snapshot source revisions and current shape/version context
  -> run the configured OWL reasoner
  -> write graph/reasoning-run/{run_id} metadata when enabled
  -> write graph/reasoning-result/{run_id} if requested
  -> persist semantic_reasoning_runs
  -> promote current reasoning pointer for graph set
  -> mark dependent rule pointers stale when rules used inferred facts
```

Reasoning failure must not mutate source graphs or promote a pointer. A partial result graph from a
failed run must not become current.

## Rule Execution Flow

Rule execution can run a single rule definition, a named rule group, or all compatible rules for a graph
set.

```text
receive rule execution request
  -> resolve graph set
  -> select compatible rule definitions and versions
  -> validate language and safety profile
  -> snapshot source revisions and consumed derived pointers
  -> execute rules in deterministic order
  -> materialize generated statements in memory
  -> attach statement origin, evidence dependencies, warnings, and explanations
  -> reject output that targets source ontology/data graphs
  -> write graph/rule-run/{run_id} metadata
  -> write graph/rule-result/{run_id}
  -> persist semantic_rule_runs
  -> promote current rule pointer when requested
  -> mark projections and dependent result pointers stale
```

Rule ordering should be explicit:

- `priority` ascending,
- then rule id,
- then version.

Dependent rule groups that consume prior rule-result graphs must be modeled as separate run stages
or explicit rule-set definitions. The first implementation should avoid implicit recursive rule
execution.

## API Surface

Phase 5 extends `/api/semantic/...`.

`POST /api/semantic/graph-sets/{graph_set_id}/validation-runs`

Runs SHACL validation over a graph set. Request options include:

```json
{
  "validation_scope": "asserted_only",
  "shape_graph_iris": [],
  "inference": "none",
  "persist_report_graph": true,
  "shape_version": "sha256:..."
}
```

`POST /api/semantic/graph-sets/{graph_set_id}/reasoning-runs`

Continues the Phase 4 endpoint and requires persisted run metadata to include graph revisions,
engine version, task profile, and missing-evidence warning summary.

`POST /api/semantic/rule-definitions`

Creates or updates a versioned rule definition. The API validates language, body shape, safety
profile, output predicates, and graph role declarations.

`GET /api/semantic/rule-definitions`

Lists rule definitions by status, language, owner, or graph-set applicability.

`POST /api/semantic/graph-sets/{graph_set_id}/construct-runs`

Runs one approved SPARQL CONSTRUCT template and writes a rule-result graph. This endpoint may be
implemented as a specialized rule run with `language="sparql_construct"`.

`POST /api/semantic/graph-sets/{graph_set_id}/rule-runs`

Runs one rule, a rule group, or all compatible rules for the graph set.

`GET /api/semantic/rule-runs/{run_id}`

Returns run status, input signature, result graph, generated statement count, warnings, audit
status, and explanation summary.

`GET /api/semantic/validation-runs/{run_id}`

Returns validation run status, conforms flag, report graph IRI, summary, graph-set signature, shape
version, and staleness state.

`POST /api/semantic/derived-results:reconcile`

Extends Phase 4 reconciliation to cover validation report staleness, rule-definition version
changes, rule engine version changes, and upstream reasoning pointer changes.

## MCP Surface

Add MCP tools only for stable agent workflows:

- describe a graph set's current validation, reasoning, and rule status,
- run graph-set validation,
- run graph-set reasoning,
- submit or update a platform DSL rule definition,
- run a named rule definition or rule group,
- inspect missing-evidence dependencies for a derived result.

Do not expose unrestricted SPARQL CONSTRUCT execution through MCP. Agents may submit rule
definitions or governed semantic edits, but the platform must validate and version them first.

## Service Design

Add or extend service boundaries:

```text
SemanticValidationService
  -> resolve graph-set validation scope
  -> run pySHACL
  -> persist report graph and operational run metadata
  -> compute validation staleness

SemanticReasoningService
  -> execute OWL reasoner over graph sets
  -> persist run/result graphs
  -> promote reasoning pointers
  -> expose reasoner task profiles and warnings

SemanticRuleDefinitionService
  -> validate rule language and safety profile
  -> create immutable rule versions
  -> retire or activate versions

SemanticConstructDerivationService
  -> validate and execute approved CONSTRUCT templates
  -> capture bindings and generated statements
  -> enforce graph-set and result-limit policy

SemanticRuleExecutionService
  -> execute platform DSL rules
  -> propagate evidence dependencies
  -> write rule-run and rule-result graphs
  -> promote rule pointers

SemanticMissingEvidenceService
  -> inspect input statement annotations
  -> attach warning annotations to generated statements
  -> summarize missing-evidence dependencies for read models
```

`SemanticService` may continue to orchestrate API calls, but the implementation should move
path-specific logic into these services as the code grows.

Extend `RdfStoreRepository` with helpers where needed:

```python
construct_sparql(query: str, timeout_seconds: float, limit: int) -> ConstructResult
insert_graph(graph_iri: str, content: str, format: str) -> UpdateResult
```

The repository must keep read CONSTRUCT execution separate from SPARQL Update. Writing generated
statements to result graphs happens through a controlled service operation.

## Staleness Model

Phase 5 completes validation staleness and expands rule staleness.

Validation report staleness triggers:

- data graph revision changes,
- shape graph revision changes,
- graph-set membership changes,
- SHACL inference mode or engine version changes,
- validation scope changes,
- shape version changes.

Reasoning result staleness triggers from Phase 4 remain in force. Phase 5 adds:

- reasoner task profile changes,
- reasoner ontology profile changes,
- missing-evidence dependency state changes when the reasoning task includes data realization or
  data entailment.

Rule result staleness triggers:

- source graph revision changes,
- graph-set membership changes,
- rule definition body or version changes,
- rule activation/retirement changes in the executed group,
- rule engine version changes,
- upstream reasoning pointer changes when `uses_inferred_facts=true`,
- upstream rule pointer changes when the rule group consumes previous rule results,
- missing-evidence dependency state changes.

Stale result graphs remain inspectable, but read APIs must label them stale unless the caller
explicitly asks to include stale derived results.

## Query and Read Semantics

Read surfaces must preserve origin:

- `asserted` for source ontology/data assertions,
- `owl_inferred` for reasoning-result statements,
- `rule_derived` for business-rule statements,
- `construct_derived` for SPARQL CONSTRUCT statements,
- `workflow_derived` for state-machine outputs,
- `validation_report` for SHACL report statements.

Merged graph-set query helpers may include derived result graphs, but responses must include:

- source graph or result graph IRI,
- assertion kind,
- run id when derived,
- current/stale pointer status,
- evidence status,
- missing-evidence dependency warnings,
- review/audit status when applicable.

## Test Strategy

Default backend tests should use fake RDF stores and deterministic in-memory rule fixtures. They
should not require a live Oxigraph service or a real OWL reasoner process.

Required tests:

- graph-set validation records source signatures, shape versions, and report graph IRIs,
- validation reports become stale when data or shape graph revisions change,
- reasoning runs do not promote a pointer after failure,
- reasoning result graphs never mutate source graphs,
- CONSTRUCT templates reject unsupported clauses and unbounded outputs,
- CONSTRUCT results are written only to rule-result graphs,
- platform DSL validation rejects unsupported operators, unsafe output predicates, and unknown
  graph roles,
- rule execution records graph revisions, engine/rule versions, generated statement count, and
  explanations,
- missing-evidence inputs propagate warnings to generated rule outputs,
- rule pointers become stale when source revisions, rule versions, or upstream reasoning pointers
  change,
- read/status responses distinguish asserted, inferred, construct-derived, rule-derived, and
  workflow-derived statements,
- `cd backend && uv run pytest` remains independent of live Oxigraph.

Optional integration tests with a live Oxigraph service should cover persisted validation report
graphs, CONSTRUCT execution against real RDF data, and result-graph export.

## Implementation Order

1. Split current validation and reasoning orchestration into dedicated services while preserving
   existing API behavior.
2. Add graph-set-aware validation endpoint and persist graph-set signatures, graph revisions,
   shape versions, and optional validation report graphs.
3. Complete validation report staleness reconciliation.
4. Harden graph-set reasoning metadata with input revisions, engine versions, task profiles, and
   missing-evidence warning summaries.
5. Add `semantic_rule_definitions` and rule definition validation.
6. Add SPARQL CONSTRUCT template execution as the first rule-result writer.
7. Add `semantic_rule_runs`, result graph writing, and rule pointer promotion.
8. Add the restricted platform DSL and compile it to deterministic query plus statement-template
   execution.
9. Add missing-evidence dependency extraction and propagation for rule outputs.
10. Add rule-result staleness reconciliation for rule versions and upstream reasoning pointers.
11. Add MCP tools for stable validation, reasoning, rule execution, and derived-warning inspection.
12. Add focused service/API tests and optional Oxigraph integration tests.

## Implementation Checklist

### 0. Documentation

- [x] State that Phase 5 separates reasoning, validation, derivation, rules, and workflow state.
- [x] State that Phase 5 does not migrate product APIs to canonical RDF writes.

### 1. Validation

- [x] Add graph-set-aware validation request/response schemas.
- [x] Add `POST /api/semantic/graph-sets/{graph_set_id}/validation-runs`.
- [x] Persist graph-set id, source signature, input revisions, shape version, and engine version.
- [x] Optionally persist SHACL report RDF to `graph/validation-run/{run_id}`.
- [x] Mark validation reports stale when data/shape graphs or validation options change.

### 2. Reasoning

- [x] Move reasoning orchestration into a dedicated `SemanticReasoningService`.
- [x] Persist input graph revisions and task profiles in reasoning run metadata.
- [x] Record missing-evidence warning summaries for data realization/entailment tasks.
- [x] Ensure failed runs never promote a current reasoning pointer.
- [x] Mark dependent rule pointers stale when a current reasoning pointer changes.

### 3. Rule Definitions

- [x] Add `SemanticRuleDefinitionModel`.
- [x] Add migration for `semantic_rule_definitions`.
- [x] Validate allowed languages: `sparql_construct`, `platform_dsl`, and
      `workflow_state_machine`.
- [x] Make rule versions immutable after activation.
- [x] Add create/list/read/update status endpoints.

### 4. SPARQL CONSTRUCT Derivation

- [x] Add approved CONSTRUCT template validation.
- [x] Reject unsafe SPARQL clauses and graph targets.
- [x] Execute CONSTRUCT with timeout and result limits.
- [x] Capture explanation bindings where practical.
- [x] Write generated statements only to `graph/rule-result/{run_id}`.

### 5. Platform DSL Rule Execution

- [x] Define the first JSON schema for the DSL.
- [x] Compile DSL conditions to deterministic graph queries.
- [x] Materialize statement templates with stable identifiers.
- [x] Record rule id, version, matched bindings, and explanation output.
- [x] Reject recursive or implicit multi-stage rules in the first implementation.

### 6. Rule Runs and Pointers

- [x] Add `SemanticRuleRunModel`.
- [x] Add migration for `semantic_rule_runs`.
- [x] Add `POST /api/semantic/graph-sets/{graph_set_id}/rule-runs`.
- [x] Persist rule-run and rule-result graph IRIs.
- [x] Promote current rule pointer after successful promoted runs.
- [x] Mark previous current rule pointers superseded.

### 7. Missing Evidence

- [x] Detect missing-evidence annotations in asserted input graphs.
- [x] Propagate missing-evidence dependencies to generated statement annotations.
- [x] Store dependency summaries in run metadata.
- [x] Surface warnings in rule-run, graph-set status, and read-model responses.

### 8. API and MCP Surface

- [x] Add rule definition endpoints.
- [x] Add rule-run and construct-run endpoints.
- [x] Add validation run read endpoint.
- [x] Extend derived-result reconciliation for validation and rule staleness.
- [x] Add MCP tools for graph-set validation, reasoning, rule execution, and warning inspection.

### 9. Tests

- [x] Add service tests for validation staleness, reasoning failure handling, CONSTRUCT safety,
      DSL validation, rule execution, pointer promotion, and missing-evidence propagation.
- [x] Add API tests for graph-set validation, rule definitions, construct runs, rule runs, and run
      status reads.
- [x] Keep default backend tests independent of live Oxigraph.
- [x] Run `cd backend && uv run pytest`.

## Completion Criteria

- [ ] `cd backend && uv run alembic upgrade head`
- [ ] `cd backend && uv run pytest`
- [ ] SHACL validation reports are persisted and tied to graph sets, graph revisions, and shape
      versions.
- [ ] OWL reasoning runs record input revisions, engine versions, task profiles, warnings, and
      persisted result graphs when requested.
- [ ] Business rule and CONSTRUCT results are auditable, reviewable, and stored separately from
      source graphs.
- [ ] Missing-evidence dependencies propagate to derived outputs and read/status surfaces.
- [ ] Tests prove reasoning, validation, CONSTRUCT derivation, and business rules do not silently
      mutate source graphs.
