# Semantic Stage 5 — Governance Design

- **Date:** 2026-07-07
- **Scope driver:** `docs/semantic/functional-semantic-load-inventory.md` Stage 5 — Governance
- **Architecture approach:** Completion of Phase 8 governance surfaces on top of the graph-native
  store. Six Phase 8 pages already exist; this stage closes the gap between Phase 8 §1–§9
  acceptance requirements and the current implementation. All work is **P / polish** — no new
  page is created, no legacy route is resurrected.
- **Status:** Implemented

## 1. Goal and Non-Goals

### Goals

1. Close every Phase 8 §1–§9 acceptance gap on the six governance pages so they read as the
   "expert and auditor view of an otherwise graph-native product" described by the inventory.
2. Add the missing backend read surfaces the governance pages need: list endpoints for
   validation/reasoning/rule runs, structured parse errors, graph-registry statement counts
   and audit timestamps, projection staleness scalar, status-endpoint stale-derived count.
3. Wire every new field into the existing typed API client (`frontend/src/semanticApi.ts`) and
   typed DTO layer (`frontend/src/types.ts`), preserving the Phase 8 envelope shapes.
4. Add the missing Playwright governance coverage that the integration test plan §10 already
   enumerates (`semantic-governance.spec.ts` exists but does not yet exercise run history,
   parse-error display, stale-projection tile, or SPARQL prefilled).
5. Complete the i18n key set under the existing flat-string convention so every visible string
   on the six pages has a zh translation.

### Non-Goals

- No new top-level stage. The `governance` workspace stage stays as the single entry; the six
  existing tabs (`graph-governance`, `named-graphs`, `graph-sets`, `semantic-edits`,
  `semantic-runs`, `semantic-import-export`) are the entire surface.
- No new graph mutation path. Stage 5 only reads through read models, list endpoints, and
  existing `/edits`, `/graph-sets`, `/graphs/{iri}/editability` writes.
- No schema migration. `SemanticGraphRegistryRead` gets new fields but they are derived from
  existing store state at request time; no new column is added.
- No revival of legacy `/versions`, `/proposals`, `/knowledge-conflicts`. Those remain deleted
  per Stages 1–4.
- No introduction of a structured RDF parser dependency for parse errors. We surface
  `rdflib`'s existing line/column information when present, and fall back to a flat message
  when not.
- Stage 5 status is `Implemented` after backend pytest, frontend build, and governance
  Playwright smoke checks passed on 2026-07-07.

## 2. Locked-In Decisions

| Decision | Resolution | Source |
| --- | --- | --- |
| Run history endpoint shape | `GET /api/semantic/{validation,reasoning,rule}-runs?graph_set_id=...&limit=N` returning a `*RunListResponse{items, summary}` envelope mirroring the audit list. | Phase 8 §3, §7; this spec §4.1 |
| Projection staleness scalar | Extend `GET /api/semantic/projections/status` to return `stale_projection_count: int` alongside the existing `stale: list[str]`. | Phase 8 §1 "stale projection warning count" |
| Graph registry new fields | Add `statement_count: int \| None` and `latest_audit_at: ISO8601 \| None` to `SemanticGraphRegistryRead`. Computed at request time from the canonical store + audit log; nullable when not yet computed. | Phase 8 §2 column list |
| Parse error structure | Add `line: int \| None`, `column: int \| None` to `SemanticEditPreviewResponse.error` (new optional object) by extracting from rdflib exception strings. Flat message preserved when extraction fails. | Phase 8 §8 "backend line/column parse errors" |
| Stale derived count on status | Add `stale_derived_count: int` to `SemanticGovernanceStatusResponse.derived`. Counted from the existing `derived_pointers` walk. | Phase 8 §1 stale derived |
| SPARQL prefilled | `SemanticImportExportPage` accepts a `?graph_set=...&prefill=...` URL param. The SPARQL pane seeds its textarea with `FROM NAMED <graph set member>` clauses derived from the graph set members. No backend change. | Phase 8 §3 "Open SPARQL query prefilled" |
| Edit-workbench parse-error UI | Render a `<ParseErrorBanner line column message />` above the editor when the preview response carries structured error fields. Keep the existing flat error notice as fallback. | Phase 8 §8 accessibility |
| Audit-shape preview | Render the canonical-write audit envelope (`{actor, reason, target_graph, evidence_binding, warnings}`) as a read-only JSON-like card on successful preview. No new API call. | Phase 8 §8 audit record shape |
| Run-history UI | New `<RunHistoryTable kind scope=graph_set_id />` reused across GraphSetPage and SemanticRunsPage. Single column shape: kind, conforms/consistency/generated-count, scope, started_at, finished_at, staleness, superseded flag, link to detail. | Phase 8 §7 |
| Evidence binding in workbench | Reuse the existing `EvidenceBindingPanel` component (already used by FactAudit). Wire it to the `evidence_binding` slot of `/edits` preview/apply. | Stage 4 §7.4 |
| i18n convention | Flat literal-English keys under the existing `// Phase 8 — semantic governance` section in `frontend/src/i18n/zh.ts`. No nesting, no `governance.*` prefix. | Existing convention |

## 3. Shared Foundations

These capabilities are already in place from Stages 1–4 and Stage 5 builds on them without
modification:

### 3.1 `SemanticReadModelService`

Dispatch surface at `backend/app/services/semantic_read_model.py`. Stage 5 does not register
new read-model templates; it only adds list endpoints and field extensions. Existing
`owl-consistency-summary` (Stage 4 §4.3) continues to back the OWL consistency section on
`GraphGovernancePage`.

### 3.2 Canonical write envelope

`submit_semantic_edit` and `compile_and_apply_canonical_command` continue to be the only
mutation path. Stage 5 surfaces more of their existing return shape (warnings, stale derived
pointers, audit envelope) without changing the write contract.

### 3.3 Graph registry repository

`SemanticGraphRegistryRepository` at `backend/app/repositories/semantic_graph_registry.py`
already returns graph rows with `revision`, `content_hash`, `derived_pointers`. Stage 5
extends the read path to also compute `statement_count` (via Oxigraph `SELECT COUNT(*)`) and
`latest_audit_at` (via the existing audit log query).

### 3.4 Projection job + status endpoint

`/api/semantic/projection-jobs` and `/api/semantic/projections/status` exist
(`semantic.py:1380-1460`). They return `{manifests, stale, missing}` where `stale` is a list
of graph-set IDs. Stage 5 adds the scalar count.

### 3.5 Frontend infrastructure

- `frontend/src/semanticApi.ts` — typed API client used by every governance page.
- `frontend/src/types.ts:501-806` — Phase 8 DTOs already cover the existing envelope.
- `frontend/src/components/semantic/` — AssertionKindBadge, GraphIriLabel,
  GraphEditabilityToggle, GraphDeltaViewer, ValidationReportPanel, ReasoningResultPanel,
  RuleResultPanel, EvidenceBindingPanel, GraphSetSelector, SemanticWarningList.
- `frontend/tests/semantic-governance.spec.ts` — Playwright scaffold with `page.route` mocks.

## 4. Backend Changes

All routes live under the existing `/api/semantic` prefix. New endpoints follow the existing
naming convention (`*-runs`, `*-runs/{id}`, `projections/status`).

### 4.1 Run history list endpoints

`GET /api/semantic/validation-runs?graph_set_id=...&kind=...&limit=...&offset=...`

`GET /api/semantic/reasoning-runs?graph_set_id=...&kind=...&limit=...&offset=...`

`GET /api/semantic/rule-runs?graph_set_id=...&kind=...&limit=...&offset=...`

All three return `{items: [<existing run schema>], summary: {total, stale_count,
superseded_count}}`. The `kind` filter is the existing task kind (e.g. `shacl`, `owl`,
`classification`, `consistency`, `missing-evidence`).

`kind` is optional. `graph_set_id` is optional. When both omitted, the endpoint returns the
global latest N (default `limit=50`). Authentication and access control follow the existing
`_require_reader` / `_require_writer` decorators.

Backend implementation reuses the existing `SemanticValidationRunRepository.list_runs(...)`
which today only supports `get(run_id)`. We add `list_runs(graph_set_id=None, kind=None,
limit=50, offset=0)` returning `(items, total)`. The repository already has the necessary
indexes on `(graph_set_id, started_at DESC)` and `(kind, started_at DESC)`.

### 4.2 Projection status scalar

`GET /api/semantic/projections/status` extends its response:

```python
class ProjectionStatusResponse(BaseModel):
    manifests: list[ProjectionManifestRead]
    stale: list[str]                        # graph set IDs (unchanged)
    stale_projection_count: int             # NEW — len(stale) but exposed as scalar
    missing: list[str]                      # unchanged
```

This is a non-breaking addition. Existing callers can ignore the new field.

### 4.3 Graph registry new fields

```python
class SemanticGraphRegistryRead(BaseModel):
    # existing fields preserved
    graph_iri: str
    label: str
    category: GraphCategory
    owner_type: str
    owner_id: str | None
    revision: int
    content_hash: str
    derived_pointers: list[DerivedPointer]
    editable: bool
    editability_reason: str
    metadata: dict[str, Any]
    mutable_by_direct_edit: bool
    # NEW
    statement_count: int | None
    latest_audit_at: datetime | None
```

`statement_count` is computed by issuing `SELECT (COUNT(*) AS ?c) WHERE { GRAPH <iri> { ?s ?p ?o } }`
against Oxigraph. Cached per request (no in-process cache). Nullable when the graph is not
materialized in Oxigraph (e.g. policy-only graph).

`latest_audit_at` is the most recent `SemanticEditAuditRow.finished_at` touching this graph
(via the audit→delta→target_graph index). Nullable when no audit exists.

### 4.4 Status endpoint stale derived count

```python
class SemanticGovernanceDerivedBlock(BaseModel):
    # existing fields preserved
    reasoning: DerivedPointer | None
    rules: DerivedPointer | None
    missing_evidence: dict[str, Any]
    # NEW
    stale_derived_count: int
```

The count is computed by walking the existing `derived_pointers` per graph set and counting
those whose `source_signature` no longer matches the asserted graphs. The walk already
happens inside `_compose_graph_set_staleness`; we surface its result on `/status`.

### 4.5 Parse error structure

```python
class SemanticEditParseError(BaseModel):
    message: str
    line: int | None = None
    column: int | None = None

class SemanticEditPreviewResponse(BaseModel):
    # existing fields preserved
    audit_id: str | None
    delta: GraphDelta | None
    graph_revisions: dict[str, int] | None
    stale_derived_pointers: list[DerivedPointer]
    validation: ValidationResult | None
    warnings: list[SemanticWarning]
    # NEW — only set when parse failed
    parse_error: SemanticEditParseError | None = None
    # existing convenience flat field kept for backwards compat
    error: str | None = None
```

`_format_parse_error` in `backend/app/services/semantic.py:596` is extended to extract
`line`/`column` from rdflib's exception text (it prints `at line N, column M` in most cases).
When extraction fails, both fields stay `None` and only `message` is populated.

### 4.6 Backend tests

For each new field/endpoint, add a backend test under `backend/tests/semantic/`:

- `test_validation_runs_list.py` — list endpoint returns items in started_at DESC order,
  filters by graph_set_id and kind.
- `test_reasoning_runs_list.py`, `test_rule_runs_list.py` — same shape.
- `test_projections_status_scalar.py` — `stale_projection_count == len(stale)`.
- `test_graph_registry_extended_fields.py` — `statement_count` matches Oxigraph COUNT(*);
  `latest_audit_at` matches the latest audit touching the graph.
- `test_status_stale_derived_count.py` — count matches the existing staleness walk.
- `test_edit_preview_parse_error_structure.py` — invalid Turtle returns `{message, line,
  column}` with both numbers populated; non-rdf exception returns line/column None.

## 5. Frontend Rebuilds

All page paths and current line counts are listed in the inventory research report. Each
rebuild adds missing Phase 8 acceptance items only; no page is rewritten from scratch.

### 5.1 `GraphGovernancePage`

| Phase 8 §1 requirement | Current state | Stage 5 action |
| --- | --- | --- |
| graph counts by category | present | unchanged |
| editable vs locked count (real ontology/data) | partial — shows editable count only | split into `lockedCount` + `editableCount` tiles, driven by `/graphs` summary |
| active graph set members | present | unchanged |
| SHACL status | present | unchanged |
| OWL reasoning pointer + staleness | present | unchanged |
| rule-result pointer + staleness | present | unchanged |
| missing-evidence count | present | unchanged |
| stale projection warning count | missing | new tile reading `projections/status.stale_projection_count` |
| latest graph deltas section | missing — only edit audits shown | new section "Latest graph deltas" reading `/edits/audits?limit=5` rendered with `GraphDeltaViewer` |
| OWL consistency section | present (Stage 4 §4.3) | unchanged |
| "Run SHACL/OWL/rules" action buttons | navigate to other tabs | keep as cross-tab navigation but add inline toast "Started — see Semantic Runs" |
| "Reconcile staleness" button | present | unchanged |
| "Lock/Unlock" button | present | unchanged |
| "Export graph set" button | present | unchanged |

### 5.2 `NamedGraphsPage`

| Phase 8 §2 requirement | Current state | Stage 5 action |
| --- | --- | --- |
| columns: label, IRI, category, owner type+id, revision, editability | present | unchanged |
| column: role in selected graph set | missing | new column showing the member role when a `?graphSet=` query param is present |
| column: current/stale status | partial | promote the existing stale badge to a real column with filter |
| column: statement count | missing | new column reading `statement_count` from extended registry response |
| column: latest audit timestamp | missing | new column reading `latest_audit_at` |
| filter: category, owner type, editable/locked | present | unchanged |
| filter: stale/current | missing | new filter chip |
| filter: missing evidence | missing | new filter chip — client-side filter on `derived_pointers[].missing_evidence` |
| filter: managed/unmanaged import | missing | new filter chip on `metadata.managed == true` |
| row action: open detail | present | unchanged |
| row action: export graph | present | unchanged |
| row action: lock/unlock | present | unchanged |
| row action: inspect latest graph delta | missing | new row action button "Latest delta" → opens a drawer with `GraphDeltaViewer` from `/edits/audits?graph=...&limit=1` |
| row action: view validation/reasoning/rule dependencies | missing | new row action button "Dependencies" → opens a drawer listing the derived pointers and their staleness |
| IRI copyable | missing | wrap IRI cell in a `<CopyableIri />` component |

### 5.3 `GraphSetPage`

| Phase 8 §3 requirement | Current state | Stage 5 action |
| --- | --- | --- |
| identity / scope / status / source signature | present | unchanged |
| members by role | present | unchanged |
| required vs optional | present | unchanged |
| current effective reasoning / rule pointers | present | unchanged |
| attached validation reports | partial | wire to the new `GET /validation-runs?graph_set_id=...` |
| stale dependency explanation | present | unchanged |
| query scope segmented control (4 scopes) | missing | new `<QueryScopeSegmentedControl />` controlling the scope passed to run actions and export |
| "Add/Remove graph members" | present | unchanged |
| "Run validation/reasoning/rules over selected scope" | present | pass scope to the run trigger |
| "Export graph set as TriG or JSON-LD" | present | pass scope to export |
| "Open SPARQL prefilled to this graph set" | missing | new button → navigates to `SemanticImportExportPage` with `?tab=semantic-import-export&graphSet={id}&prefill=sparql` |

The four query scopes map to the existing `include` parameter on `/graph-sets/{id}/export`
(`asserted`, `asserted-plus-reasoning`, `asserted-plus-rules`, `full-working-view`).

### 5.4 `SemanticEditWorkbenchPage`

| Phase 8 §8 requirement | Current state | Stage 5 action |
| --- | --- | --- |
| input formats (TriG/Turtle/JSON-LD/SPARQL Update/SHACL/OWL) | present | unchanged |
| target graph selector | present | unchanged |
| graph set context selector | partial — has `GraphSetSelector` but not wired to `/edits` preview | wire the selected graph set into preview/apply request body |
| input format selector | present | unchanged |
| reason/audit note | present | unchanged |
| evidence binding panel | missing | mount existing `EvidenceBindingPanel` and pass its output as `evidence_binding` in the apply request |
| missing-evidence acknowledgement | missing | new checkbox "I acknowledge this edit produces missing-evidence markers" gating apply when preview warns |
| Validate/Preview button | present | unchanged |
| Apply button (disabled until preview ok) | partial | gate `disabled` on `preview.validation?.conforms` AND `!preview.parse_error` AND (no missing-evidence warning OR acknowledgement checked) |
| parse result with line/column | missing | new `<ParseErrorBanner />` above the editor when `preview.parse_error` is set |
| graph delta preview | present | unchanged |
| target graph editability preview | missing | new inline note "Target graph is {editable/locked}" |
| SHACL validation result preview | present | unchanged |
| platform validation result preview | present | unchanged |
| OWL reasoning impact preview (when requested) | missing | new optional checkbox "Run reasoning impact" that adds `include_reasoning_impact=true` to preview |
| stale derived results that will be created | missing | new section listing `preview.stale_derived_pointers` |
| warnings | present | unchanged |
| audit record shape preview | missing | new `<AuditRecordShapeCard />` rendering the would-be audit envelope |

### 5.5 `SemanticRunsPage`

Phase 8 §7 is the largest gap. Current page only looks up runs by ID. Stage 5 restructures
the page into two panes:

- **Left pane — Run history table.** Driven by `GET /{validation,reasoning,rule}-runs?graph_set_id=...`.
  Reuses the new `<RunHistoryTable />` component. Default graph set = active graph set from
  `/status`. Columns: kind, conforms/consistency/generated-count, scope (graph set label),
  started_at, finished_at, staleness badge, superseded flag, "Open" link.
- **Right pane — Run detail.** Existing `ValidationReportPanel` / `ReasoningResultPanel` /
  `RuleResultPanel` shown when a run is selected.

Page accepts `?kind=validation|reasoning|rule&run_id=...&graph_set=...` URL params for deep
linking. The lookup-by-ID form is preserved as a secondary action ("Look up by run ID").

Behavior rules from Phase 8 §7 enforced:

- Stale results are only readable under an explicit "Stale" badge in the table.
- Current effective pointers (from `/status`) are highlighted in the table.
- Superseded result graphs are badged "Superseded" and not labeled current.
- Failed runs show an error summary; the page never claims the source graph mutated.

### 5.6 `SemanticImportExportPage`

| Phase 8 §9 requirement | Current state | Stage 5 action |
| --- | --- | --- |
| Upload or paste RDF | present | unchanged |
| Categorize incoming graphs as import graphs | missing | new step "Categorize" — for each detected graph IRI in the parsed dataset, the user picks `ontology | data | reasoning | rule | shapes | policy | import` |
| Map imported IRIs to platform categories | missing | new step "Map IRIs" — preset mapping rules with overrides |
| Preview graph delta before promotion | missing | new step "Preview delta" — calls `/edits` preview with `validate=false` and renders `GraphDeltaViewer` |
| SHACL validate imported data | missing | new step "Validate" — calls `/edits` preview with `validate=true` |
| Optional OWL consistency check | missing | new checkbox in the Validate step that triggers a consistency reasoning run |
| Bind evidence/provenance to imported assertions | missing | new step "Bind evidence" using the existing `EvidenceBindingPanel` |
| Record import run graph + audit | present (governed edit apply) | unchanged |
| Export scope selector (asserted/reasoning/rules/full) | partial | promote the existing include flags to a segmented control matching §5.3 |
| Export formats (TriG/Turtle/JSON-LD) | present | unchanged |
| Export options (governance/evidence graphs) | present | unchanged |
| SPARQL pane accepts `?graphSet=...&prefill=sparql` | missing | when URL param present, seed the SPARQL textarea with `FROM NAMED` clauses from the graph set members |

The import flow becomes a 5-step wizard: Upload → Categorize → Map IRIs → Preview delta →
Validate & bind. Each step gates the next.

### 5.7 Routing

No new top-level route. Existing deep links `?tab=...` and `?graphSet=...` are extended:

- `?tab=semantic-runs&kind=validation&graph_set={id}` opens SemanticRunsPage with the
  validation tab preselected.
- `?tab=semantic-import-export&graphSet={id}&prefill=sparql` opens the SPARQL pane seeded.
- `?tab=semantic-edits&graph={iri}` opens the workbench with target graph preset.

### 5.8 i18n

Add the following flat keys to `frontend/src/i18n/zh.ts` under the existing `// Phase 8 —
semantic governance` section:

```
"Stale projection count"
"Locked"
"Editable"
"Latest graph deltas"
"Statement count"
"Latest audit"
"Stale / current"
"Missing evidence"
"Managed / unmanaged"
"Managed"
"Unmanaged"
"Open SPARQL prefilled"
"Open SPARQL query prefilled to this graph set"
"Run history"
"Look up by run ID"
"Superseded"
"Current"
"Line"
"Column"
"Parse error"
"Target graph is locked"
"Target graph is editable"
"Run reasoning impact"
"I acknowledge this edit produces missing-evidence markers"
"Audit record shape"
"Evidence binding"
"Categorize incoming graphs"
"Map IRIs to platform categories"
"Preview graph delta"
"Validate imported data"
"Run OWL consistency check"
"Bind evidence"
"Upload"
"Categorize"
"Map IRIs"
"Preview delta"
"Validate & bind"
"Promote"
"Assertion kind"
"OWL inferred"
"Rule derived"
"Imported"
"Review metadata"
"Policy metadata"
"Dependencies"
"Latest delta"
"Role in selected graph set"
"Query scope"
"Asserted only"
"Asserted + reasoning"
"Asserted + rules"
"Full working view"
```

Each English source string remains the key; zh value is the Chinese translation.

## 6. Error Handling

- Run list endpoints return 200 with `{items: [], summary: {total: 0, stale_count: 0,
  superseded_count: 0}}` when no runs match. They never 404 on empty filters.
- Graph registry `statement_count` and `latest_audit_at` return `null` when the underlying
  store has no data. The frontend renders `—` for null.
- Parse error extraction: if rdflib's exception text does not contain `at line N, column M`,
  both `line` and `column` are `null` and the flat `error` field still carries the message.
  The frontend renders only the message in that case.
- SPARQL prefilled: if the graph set has no members, the SPARQL pane shows an info toast "No
  members in this graph set" and falls back to the empty editor.
- Import wizard: each step's failure keeps the user on that step. The Promote button is
  disabled until every prior step passes.

## 7. Testing Strategy

### 7.1 Backend

For each item in §4.6:

- Endpoint happy path returns the expected extended schema.
- Empty filter returns 200 with empty items.
- Filters compose (`graph_set_id` + `kind`).
- New fields are nullable as documented.

Tests run under `cd backend && uv run pytest tests/semantic/`.

### 7.2 Frontend

- `npx tsc --noEmit` passes with the extended DTO types.
- `npx playwright test semantic-governance.spec.ts` passes the existing 6 cases.
- New Playwright cases (see §7.3).

### 7.3 Playwright governance coverage

Extend `frontend/tests/semantic-governance.spec.ts` with:

1. `shows stale projection count tile` — mocks `/projections/status` with `stale_projection_count: 3`, asserts the tile renders "3".
2. `shows latest graph deltas section` — mocks `/edits/audits` with 2 entries, asserts both render.
3. `named graphs table shows statement count and latest audit columns` — mocks `/graphs` with the new fields, asserts cells render.
4. `named graphs filters: stale, missing-evidence, managed` — toggles each filter chip, asserts the table filters.
5. `graph set page: query scope segmented control` — clicks each of the 4 scopes, asserts the export button carries the right `include` parameter.
6. `graph set page: SPARQL prefilled link` — clicks "Open SPARQL prefilled", asserts navigation to import-export tab with seeded textarea.
7. `edit workbench: parse error banner` — mocks `/edits` preview with `parse_error: {message, line: 3, column: 10}`, asserts banner renders with line/column.
8. `edit workbench: apply gated on preview` — asserts Apply button is disabled until preview conforms.
9. `runs page: history table` — mocks `/validation-runs?graph_set_id=...`, asserts table renders 5 rows in started_at order.
10. `runs page: stale and superseded badges` — mocks runs with staleness/superseded flags, asserts badges render.
11. `import-export: 5-step wizard` — walks through Upload → Categorize → Map IRIs → Preview → Validate, asserts each step gates the next.
12. `import-export: SPARQL prefilled via URL param` — navigates with `?prefill=sparql&graphSet=...`, asserts seeded textarea.

All cases use the existing `page.route('**/api/semantic/**', ...)` mock pattern.

## 8. Migration Strategy

This stage is **additive only**:

- All new backend response fields are optional or additive. Existing callers continue to work.
- The flat `error` field on edit preview is preserved alongside the new `parse_error` object.
- The new run history endpoints do not replace the existing `/validation-runs/{id}` lookup.
- The 5-step import wizard preserves the existing apply path; the legacy "load + apply in one
  click" path remains accessible via an "Advanced: skip wizard" link.

No data migration. No schema migration. No backwards-compat shim beyond the field
preservation noted above.

## 9. Happy-Path E2E Plan

1. Open `GraphGovernancePage`. Assert: stale projection count tile shows a number; latest
   graph deltas section shows the 5 most recent audits.
2. Click "Open named graph registry". Assert: table shows statement count and latest audit
   columns; toggle the "Stale" filter; the table filters.
3. Click a graph row's "Dependencies" action. Assert: drawer lists derived pointers with
   staleness badges.
4. Navigate to `GraphSetPage`. Click "Asserted + reasoning" scope. Click "Run reasoning".
5. Click "Open SPARQL prefilled". Assert: SPARQL pane opens with seeded `FROM NAMED` clauses.
6. Navigate to `SemanticEditWorkbenchPage`. Paste invalid Turtle. Click Preview. Assert:
   parse error banner shows "Line 3, Column 10".
7. Fix the Turtle. Click Preview again. Assert: Apply button enables.
8. Navigate to `SemanticRunsPage`. Assert: history table lists the previous reasoning run.
9. Click the run row. Assert: detail pane renders with staleness badge if applicable.
10. Navigate to `SemanticImportExportPage`. Walk the 5-step wizard. Assert: each step gates
    the next.

## 10. Implementation Order and Subagent Decomposition

Stage 5 is decomposed into six phases, each a single subagent dispatch. Phases A–B are
backend; phases C–E are frontend (split across the six pages); phase F is i18n + Playwright;
phase G is verify and status flip.

### Phase A — Backend extensions (single dispatch)

- Add `list_runs` to the three run repositories.
- Add the three `GET /{kind}-runs` list endpoints with summary envelopes.
- Extend `projections/status` with `stale_projection_count`.
- Extend `SemanticGraphRegistryRead` with the two new optional fields and the Oxigraph count
  query path.
- Extend `SemanticGovernanceStatusResponse.derived` with `stale_derived_count`.
- Extend `_format_parse_error` and `SemanticEditPreviewResponse` with structured fields.

### Phase B — Backend tests (single dispatch)

- Add the six backend test files listed in §4.6.
- Run `cd backend && uv run pytest tests/semantic/` until green.

### Phase C — Frontend pages 1–2 (parallel dispatch, two subagents)

- C1: `GraphGovernancePage` — stale projection tile, locked/editable split, latest graph
  deltas section, action toasts.
- C2: `NamedGraphsPage` — new columns, new filters, new row actions, copyable IRI.

### Phase D — Frontend pages 3–4 (parallel dispatch, two subagents)

- D1: `GraphSetPage` — query scope segmented control, run-history snippet, SPARQL prefilled
  link.
- D2: `SemanticRunsPage` — full restructure with `<RunHistoryTable />` and detail pane.

### Phase E — Frontend pages 5–6 (parallel dispatch, two subagents)

- E1: `SemanticEditWorkbenchPage` — parse error banner, evidence binding panel, audit shape
  card, apply gating, reasoning impact option.
- E2: `SemanticImportExportPage` — 5-step wizard + SPARQL prefilled wiring.

### Phase F — i18n + Playwright (single dispatch)

- Add the §5.8 i18n keys to `frontend/src/i18n/zh.ts`.
- Add the 12 Playwright cases listed in §7.3.

### Phase G — Verify and status flip (main agent)

- Run backend pytest, frontend tsc, Playwright governance spec.
- Flip the spec status from `Proposed` to `Implemented`.

### 10.1 Verification Gates

- Phase A gate: backend `uv run pytest tests/semantic/` green for the extended schemas.
- Phase B gate: backend pytest green for all new tests.
- Phase C–E gate: `cd frontend && npx tsc --noEmit` green; manual smoke of each page passes.
- Phase F gate: `cd frontend && npx playwright test semantic-governance.spec.ts` green.
- Phase G gate: end-to-end happy path §9 walked manually; commit history follows the existing
  `feat(semantic):` / `feat(frontend):` convention.

## 11. Open Questions

These do not block Stage 5 implementation and are documented for future work:

- Whether the governance stage should fold back into Modeling/Publish as sub-views once
  Stages 2–3 are fully graph-native (inventory open question §168-172). Out of scope here.
- Whether the run-history list endpoint should support cursor-based pagination. Current
  design uses offset/limit which is sufficient for the dashboard use case.
- Whether the import-wizard's "Map IRIs" step should auto-suggest categories from naming
  conventions (e.g. `.../ontology/...` → `ontology`). Deferred — Stage 5 ships with manual
  mapping only.
- Whether the OWL reasoning impact preview in the edit workbench should be a separate API
  call or a flag on the existing preview. Current design uses a flag; revisit if preview
  latency becomes an issue.
