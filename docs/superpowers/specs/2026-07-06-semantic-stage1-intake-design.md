# Semantic Stage 1 — Intake Refactor Design

- **Date:** 2026-07-06
- **Scope driver:** `docs/semantic/functional-semantic-load-inventory.md` → Stage 1 — Intake
- **Architecture approach:** Phase 6 read-model + thin composer endpoint (Approach C)
- **Status:** Approved for implementation planning

## 1. Goal and Non-Goals

### Goal

Refactor the two **P** (projection-bridge) items in Stage 1 — Intake so that all RDF-derived
state is consumed through Phase 6 read-model contracts, while non-semantic Postgres data
continues to be served by existing endpoints.

The two Stage 1 deliverables are:

1. **`BuildOverviewPage`** is rewritten to fetch a single
   `/ontologies/{id}/build-overview` endpoint that composes Phase 6 read-model output with
   Postgres brief and competency-question summaries. The workflow timeline is removed.
2. **`CompetencyQuestion validate`** is rerouted from Neo4j Cypher to SPARQL SELECT count
   over the active graph-set. The two existing `query_definition` kinds (`entity_count`,
   `relation_count`) keep their semantics; a new `sparql_count` kind supports arbitrary
   SPARQL SELECTs.

### Non-Goals

- Topology canvas. The inventory marks Topology as **R** in Stage 1 but its Rebuild Order
  entry says it lands last (pure projection over a stable graph-set). Stage 1 leaves the
  current `<EmptyState>` placeholder in place.
- `ProjectBriefPage` and Sources. Both are **K** in this stage; no work.
- Hard-removing the legacy endpoints `/ontologies/{id}/versions`,
  `/ontologies/{id}/proposals`, `/projects/{id}/build-context`. They are marked deprecated
  in Stage 1 (Deprecation response header + warning log) and removed in Stage 3 when
  Publication is rebuilt.
- `BuildOverviewPage` workflow timeline redesign. The gathering/schema_draft/.../published
  model is retired by ADR 0004; the timeline is removed, not preserved.

## 2. Locked-In Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Topology scope | Defer to Stage 2 / Rebuild Order step 6 | Rebuild Order says Topology lands last; the only **R** in Stage 1 cannot block on Stage 2 outputs |
| Validate semantics | SPARQL SELECT count, preserve `entity_count`/`relation_count`, add `sparql_count` | Minimal semantic drift; new kind covers arbitrary queries |
| BuildOverview migration | Hard switch; legacy endpoints deprecated, not removed in Stage 1 | Versions table is still consumed by Stages 2–3; hard delete waits until Stage 3 |
| Workflow timeline | Remove entirely; replace with graph-set status panel | ADR 0004 retires draft→published model |
| Backend architecture | Approach C — Phase 6 read-model for RDF signals + thin composer endpoint for Postgres composition | Respects inventory's read-model discipline without bloating SPARQL |

## 3. Architecture Overview

Two parallel work tracks with no shared dependencies:

```
Track 1 — BuildOverview
─────────────────────────
frontend/BuildOverviewPage.tsx (rewrite)
  └─ GET /ontologies/{ontology_id}/build-overview    ← new composer endpoint

backend/app/api/interview.py (extend)
  └─ GET /ontologies/{ontology_id}/build-overview    ← new route
        ├─ Postgres: brief completeness + competency-question counts
        ├─ RDF via SemanticReadModelService.read_model(gs_id, "graph-set-staleness")
        └─ Compose BuildOverviewResponse

backend/app/services/semantic_sparql_templates.py (extend)
  └─ new template `graph-set-staleness` (composer-driven; SPARQL only fetches
     missing-evidence count)

Track 2 — CompetencyQuestion validate
──────────────────────────────────────
frontend/CompetencyQuestionsPage.tsx (minor)
  └─ query_definition editor adds sparql_count kind

backend/app/services/interview.py::run_question_validation (rewrite)
  ├─ kind=entity_count|relation_count → SPARQL SELECT count over asserted_data graphs
  └─ kind=sparql_count → user-provided SELECT, validated as read-only, hard timeout
```

### Common Constraints

- All RDF-derived data flows through `/graph-sets/{id}/read-models/{name}`. No direct
  RDF-store reads from product endpoints.
- The three legacy endpoints gain `Deprecation: true` and `Sunset:` hint headers in
  Stage 1. They are not deleted.
- Topology placeholder stays untouched.
- New routes are covered by the semantic language integration smoke suite
  (`docs/semantic/semantic-language-integration-test-plan.md`).

## 4. Track 1 — `BuildOverviewPage` Refactor

### 4.1 Read-Model Template `graph-set-staleness`

Registered in `backend/app/services/semantic_sparql_templates.py`:

```python
ReadModelTemplate(
    name="graph-set-staleness",
    projection_version="semantic-read-v1",
    required_roles=("asserted_ontology", "asserted_data"),
    needs_reasoning=True,
    needs_rules=True,
    default_limit=1,
    assertion_kind="asserted",
    evidence_status="mixed",
    body="# composer-driven; SPARQL only fetches missing-evidence count",
)
```

**Field set `summary`** (envelope `items[0]`):

```json
{
  "graph_set_id": "...",
  "members": [
    {
      "iri": "https://.../graph/ontology/abc",
      "role": "asserted_ontology",
      "editable": true,
      "validation_stale": false,
      "reasoning_stale": true,
      "rule_stale": false,
      "last_semantic_edit_at": "2026-07-05T09:12:00Z"
    }
  ],
  "missing_evidence_count": 12,
  "last_semantic_edit_at": "2026-07-05T09:12:00Z"
}
```

**Field set `detail`** adds per-member derived pointer metadata:
`{became_current_at, engine_name, engine_version, rule_version, shape_version}` for each
of validation / reasoning / rule.

**Implementation note.** Staleness, editability, and last-semantic-edit timestamps live in
Postgres (`semantic_graph_registry`, `semantic_derived_result_pointers`,
`semantic_edit_audit`). They are not SPARQL-queryable. The template body is therefore a
marker; the real assembly happens in a dedicated branch of `SemanticReadModelService` that:

1. Resolves graph-set members via `graph_registry.list_members(graph_set_id)`.
2. Looks up the latest `SemanticDerivedResultPointer` per (graph_set, result_kind) and
   compares `became_current_at` against the latest `SemanticEditAudit` affecting each
   member graph. A pointer is stale when the audit is newer than the pointer, or when the
   pointer is missing.
3. Runs a single SPARQL `SELECT (COUNT(*) AS ?c) WHERE { GRAPH ?g { ?s <op>evidenceStatus "missing_evidence" } VALUES ?g { ... } }`
   to count missing-evidence triples across asserted_data members.
4. Composes the envelope. Items list contains exactly one entry; pagination shape is the
   standard Phase 6 envelope.

This keeps the templates registry honest (every read model has a template) without
forcing a complex aggregation SPARQL.

### 4.2 Composer Endpoint `/ontologies/{id}/build-overview`

```
GET /ontologies/{ontology_id}/build-overview
  → 200 BuildOverviewResponse
  → 404 if ontology has no active graph-set (scope_type='ontology', scope_id=ontology_id,
       status='active')
  → 503 if RDF store is unreachable
```

**Response shape:**

```json
{
  "ontology_id": "...",
  "graph_set": { /* § 4.1 summary content */ },
  "project_brief": {"completeness": 0.66, "missing_fields": ["scope", "core_concepts"]},
  "competency_questions": {
    "total": 7,
    "by_status": {"draft": 2, "approved": 1, "testable": 0, "passed": 4, "failed": 0}
  },
  "next_actions": [
    {"key": "complete_brief", "label": "完善 Project Brief",
     "detail": "2 个字段待处理", "tab": "brief"}
  ]
}
```

**`next_actions` derivation rules (server-side, deterministic order):**

| Priority | Condition | Action |
| --- | --- | --- |
| 1 | `project_brief.completeness < 1` | `complete_brief` |
| 2 | `competency_questions.by_status.draft > 0` | `approve_questions` |
| 3 | any graph-set member `validation_stale` | `recompute_validation` |
| 4 | any graph-set member `reasoning_stale` or `rule_stale` | `recompute_derived` |
| 5 | `missing_evidence_count > 0` | `audit_missing_evidence` |

Top three are returned. Empty list is valid.

### 4.3 Frontend `BuildOverviewPage`

**Removed:** workflow timeline, "当前版本" card, "最近变更批次" card, deterministic blockers
section's proposal branch.

**Retained:** Brief completeness metric, competency-questions count metric, refresh button,
error/retry Alert.

**Added:**
- **Active graph-set status card** — member graphs with editability toggle and
  validation/reasoning/rule staleness badges.
- **Derived freshness card** — three columns (validation / reasoning / rule), each showing
  `became_current_at` and stale state, with a "Go to Governance" link.
- **Missing-evidence metric** — count + link to Evidence Explorer (link target moves to
  FactAudit in Stage 2).
- **Next-actions card** — renders server `next_actions` directly.

**Type changes:** `frontend/src/pages/workbenchTypes.ts` adds `BuildOverviewResponse`,
`GraphSetMemberStaleness`, `NextAction`.

### 4.4 Deprecation Policy

In Stage 1 the three legacy routes gain:

```python
response.headers["Deprecation"] = "true"
response.headers["Sunset"] = "Sat, 1 Nov 2026 00:00:00 GMT"  # target Stage 3 release
logger.warning("deprecated route called: %s", request.url.path)
```

Routes are otherwise unchanged. Hard removal is tracked under Stage 3.

## 5. Track 2 — `CompetencyQuestion validate` Refactor

### 5.1 `query_definition` Schema

```typescript
type QueryDefinition =
  | { kind: "entity_count"; class_id: string; min_count: number }
  | { kind: "relation_count"; relation_type_id: string; min_count: number }
  | { kind: "sparql_count"; sparql: string;
      expected_min?: number; expected_max?: number };
```

The `source_brief_fields` and `importance` fields on `CompetencyQuestion` are unchanged.

### 5.2 Backend Implementation (`run_question_validation`)

The function resolves the ontology's active graph-set, then dispatches on `kind`:

#### `entity_count`

Phase 2 IRI mapping resolves `class_id` (legacy UUID accepted) to a full IRI. The
asserted_ontology graph is included in the `VALUES ?g` list alongside asserted_data
members, because subclass hierarchy lives there:

```sparql
SELECT (COUNT(DISTINCT ?e) AS ?count) WHERE {
  VALUES ?g { <ontology-graph-iri> <data-graph-iris...> }
  GRAPH ?g { ?e rdf:type/rdfs:subClassOf* <class_iri> }
}
```

Pass when `count >= min_count`.

#### `relation_count`

Phase 2 IRI mapping resolves `relation_type_id` to its predicate IRI. SPARQL:

```sparql
SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE {
  VALUES ?g { <member-data-graph-iris> }
  GRAPH ?g { ?s <predicate_iri> ?o }
}
```

Pass when `count >= min_count`.

#### `sparql_count`

The user-provided SPARQL must:

- Parse with first significant keyword `SELECT` (case-insensitive). `ASK`, `CONSTRUCT`,
  `DESCRIBE`, `INSERT`, `DELETE`, `LOAD`, `CLEAR`, `DROP`, `CREATE`, `MODIFY`, `ADD`,
  `MOVE`, `COPY` are rejected with 422 `error="only SELECT allowed"`.
- Be read-only by keyword allow-list; any forbidden keyword in the body
  (`INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|MODIFY`) is rejected with the same error.
- Be scoped to the active graph-set's asserted_data members. The backend rewrites the
  query to inject `FROM` clauses (or wraps in `GRAPH ?g { … } VALUES ?g {…}`) so the
  user cannot read other graphs.
- Return a result whose first row's first column (or column named `count`) is an integer.
  Otherwise 422 `error="sparql result missing count column"`.
- Complete within `competency_question_sparql_timeout_seconds` (default 5s, configurable).
  Timeout → 422 `error="sparql_timeout"`.

Pass when `expected_min` and `expected_max` are satisfied:
- both provided → `expected_min <= count <= expected_max`
- only `expected_min` → `count >= expected_min`
- only `expected_max` → `count <= expected_max`
- neither → 422 at request time (must provide at least one bound)

#### Result recording

On success: `status` becomes `passed` or `failed`; `validation_result` is overwritten with:

```json
{
  "kind": "entity_count" | "relation_count" | "sparql_count",
  "matches": 42,
  "expected_min": 5,
  "expected_max": null,
  "passed": true,
  "validated_at": "2026-07-06T..."
}
```

On `sparql_count` rejection (non-SELECT, forbidden keyword, timeout, missing count column,
syntax error): `status="failed"`, `validation_result={error, validated_at}`. The HTTP
response is 422 with the same error body so the frontend can render the cause.

The 409 "only testable questions can be validated" guard remains.

### 5.3 Frontend `CompetencyQuestionsPage`

The query-definition editor in the modal gains a `kind` selector:

- `entity_count` — class_id dropdown (from ontology classes), min_count number input
- `relation_count` — relation_type_id dropdown, min_count number input
- `sparql_count` — textarea for SPARQL, expected_min / expected_max optional numbers

Existing UI behaviors (status transitions, active toggle, position move) are unchanged.

## 6. Error and Boundary Behavior

| Scenario | HTTP | Frontend |
| --- | --- | --- |
| Ontology has no active graph-set | 404 `{"detail": "ontology has no active graph-set"}` | BuildOverview shows guidance card linking to GraphSetPage |
| RDF store unreachable | 503 | BuildOverview shows retry button (existing Alert) |
| `sparql_count` not SELECT | 422 `{"error": "only SELECT allowed"}` | CompetencyQuestionsPage shows Alert with error |
| `sparql_count` write keyword | 422 `{"error": "only SELECT allowed"}` | same |
| `sparql_count` timeout | 422 `{"error": "sparql_timeout"}` | same |
| `sparql_count` syntax error | 422 `{"error": "<truncated oxigraph message>"}` | same |
| `sparql_count` missing bounds | 422 `{"error": "expected_min or expected_max required"}` | shown at submit time |
| `class_id`/`relation_type_id` unresolved in Phase 2 mapping | 422 `{"error": "<id> unresolved in phase2 mapping"}` | Alert |
| Read-model staleness fields missing | 200, fields null | gray "unknown" badge; not an error |
| Question not in `testable` status | 409 `{"detail": "Only testable questions can be validated"}` | unchanged |

## 7. Testing Strategy

### 7.1 Backend Unit Tests (pytest)

New test modules / additions:

- `backend/tests/test_semantic_read_model.py` — extend with:
  - `test_graph_set_staleness_summary` — full fixture; assert envelope
  - `test_graph_set_staleness_no_derived_pointers` — fields null, no crash
  - `test_graph_set_staleness_missing_evidence_count` — count matches fixture triples
- `backend/tests/test_interview_api.py` — extend with:
  - `test_build_overview_endpoint_complete` — graph-set + brief + questions + actions
  - `test_build_overview_endpoint_no_graph_set` — 404
  - `test_build_overview_next_actions_each_branch` — parametric for the 5 rules
- `backend/tests/test_interview_service.py` — extend with:
  - `test_run_question_validation_entity_count_sparql`
  - `test_run_question_validation_relation_count_sparql`
  - `test_run_question_validation_sparql_count_pass`
  - `test_run_question_validation_sparql_count_rejects_construct`
  - `test_run_question_validation_sparql_count_rejects_insert`
  - `test_run_question_validation_sparql_count_rejects_ask`
  - `test_run_question_validation_sparql_count_timeout`
  - `test_run_question_validation_sparql_count_missing_count_column`
  - `test_run_question_validation_phase2_iri_mapping`

### 7.2 Integration Smoke (`docs/semantic/semantic-language-integration-test-plan.md`)

New entries under the existing Stage 1 / Intake section:

- `GET /ontologies/{id}/build-overview` — 200 field coverage
- `GET /graph-sets/{gs}/read-models/graph-set-staleness` — envelope shape contract
- `POST /competency-questions/{id}/validate` for each of `entity_count`,
  `relation_count`, `sparql_count`

### 7.3 Playwright (frontend)

- `BuildOverviewPage` renders graph-set status panel with members, staleness badges,
  missing-evidence metric
- `BuildOverviewPage` shows the correct `next_action` when reasoning is stale
- `BuildOverviewPage` shows guidance card when ontology has no active graph-set (mock
  the 404)
- `CompetencyQuestionsPage` opens the editor, selects `sparql_count`, submits, observes
  status pass/fail transition

## 8. Out-of-Scope / Future Trackers

- **Legacy endpoint hard removal** — Stage 3 (Publication rebuild) removes
  `/ontologies/{id}/versions`, `/ontologies/{id}/proposals`, `/projects/{id}/build-context`.
- **Topology canvas** — Stage 2 / Rebuild Order step 6.
- **Read-model field set `detail` consumers** — Stage 1 implements `detail` server-side
  but no UI consumes it yet; this is deliberate to keep Stage 1 frontend focused.
- **Migration of existing `entity_count`/`relation_count` data** — none required; the
  schema shape is unchanged, only the execution engine changes.
- **SHACL shape validation kind** — not added in Stage 1. Reserved for Stage 2 when
  ClassesPage rebuild makes shape IDs first-class.

## 9. Open Questions for Stage 1 Implementation

These will be resolved during plan writing, not before:

- **Deprecation `Sunset` date.** Pinned in § 4.4 to a placeholder Stage 3 release date.
  The implementation plan should confirm the actual release cadence before merging.
- **`competency_question_sparql_timeout_seconds` setting name.** May collide with existing
  settings; the plan should confirm the canonical settings namespace.
- **SPARQL query rewriting strategy.** Injecting `FROM` vs. wrapping in
  `GRAPH ?g { … } VALUES ?g {…}` — the plan should pick one and document why; Oxigraph
  has subtle differences in how each handles graphs not in the store.
