# Semantic Stage 5 — Governance Implementation Plan

- **Date:** 2026-07-07
- **Spec:** `docs/superpowers/specs/2026-07-07-semantic-stage5-governance-design.md`
- **Inventory:** `docs/semantic/functional-semantic-load-inventory.md` Stage 5
- **Status:** In progress

Plan is decomposed into seven phases (A–G). Phases A and B are sequential (backend must land
and test before frontend consumes). Phases C, D, E run as three parallel subagent pairs.
Phase F runs after C–E. Phase G is the main agent's verify pass.

## Phase A — Backend extensions (single dispatch)

Single subagent. One commit at the end of the phase.

### Task A1: Run history list endpoints

- `backend/app/repositories/semantic_validation_run_repository.py` — add
  `list_runs(graph_set_id, kind, limit, offset) -> tuple[list, int]`.
- Same for `semantic_reasoning_run_repository.py` and `semantic_rule_run_repository.py`.
- `backend/app/api/schemas.py` — add `ValidationRunListResponse`,
  `ReasoningRunListResponse`, `RuleRunListResponse` with `{items, summary}` envelope. Summary
  shape: `{total, stale_count, superseded_count}`.
- `backend/app/api/semantic.py` — add `GET /validation-runs`, `GET /reasoning-runs`,
  `GET /rule-runs` with query params `graph_set_id`, `kind`, `limit=50`, `offset=0`. Reuse
  existing `_require_reader` decorator.

### Task A2: Projection status scalar

- `backend/app/api/schemas.py` — add `stale_projection_count: int` to
  `ProjectionStatusResponse`.
- `backend/app/api/semantic.py` `/projections/status` handler — set it to `len(stale)`.

### Task A3: Graph registry extended fields

- `backend/app/api/schemas.py` — add `statement_count: int | None = None` and
  `latest_audit_at: datetime | None = None` to `SemanticGraphRegistryRead`.
- `backend/app/services/semantic_graph_registry_service.py` (or wherever the registry list
  is composed) — for each graph, issue `SELECT (COUNT(*) AS ?c) WHERE { GRAPH <iri> { ?s ?p ?o } }`
  against Oxigraph via the existing repository; query the latest audit touching the graph
  via `SemanticEditAuditRepository.list_by_graph(graph_iri, limit=1)`.

### Task A4: Status stale derived count

- `backend/app/api/schemas.py` — add `stale_derived_count: int` to the
  `SemanticGovernanceStatusResponse.derived` block.
- `backend/app/api/semantic.py` `/status` handler — reuse the existing staleness walk
  (`_compose_graph_set_staleness` or equivalent) and count stale pointers.

### Task A5: Parse error structure

- `backend/app/services/semantic.py` `_format_parse_error` — extract `line`/`column` from
  the exception string using a regex matching rdflib's `at line N, column M` format. Return
  `(message, line, column)` tuple.
- `backend/app/api/schemas.py` — add `SemanticEditParseError{message, line, column}` and
  `parse_error: SemanticEditParseError | None = None` to `SemanticEditPreviewResponse`.
- Wire the structured field into the `/edits` preview handler.

### Task A6: Phase A commit

Single commit:

```
feat(semantic): Stage 5 backend extensions (list runs, projection scalar,
graph registry fields, status stale count, parse error structure) (Stage 5 §4)
```

## Phase B — Backend tests (single dispatch)

Single subagent. One commit.

### Task B1: Six backend test files

- `backend/tests/semantic/test_validation_runs_list.py`
- `backend/tests/semantic/test_reasoning_runs_list.py`
- `backend/tests/semantic/test_rule_runs_list.py`
- `backend/tests/semantic/test_projections_status_scalar.py`
- `backend/tests/semantic/test_graph_registry_extended_fields.py`
- `backend/tests/semantic/test_status_stale_derived_count.py`
- `backend/tests/semantic/test_edit_preview_parse_error_structure.py`

Each file: 2–4 cases covering happy path + edge case (empty / null / error).

### Task B2: Phase B commit

```
test(semantic): Stage 5 backend coverage (Stage 5 §4.6)
```

## Phase C — Frontend GraphGovernancePage + NamedGraphsPage (two parallel subagents)

### Task C1: GraphGovernancePage

File: `frontend/src/pages/GraphGovernancePage.tsx`.

- Add tile "Stale projection count" reading `projectionsStatus.stale_projection_count`.
- Split editable tile into `editableCount` + `lockedCount`.
- Add "Latest graph deltas" section reading `/edits/audits?limit=5`, render via
  `GraphDeltaViewer`.
- Replace action button side-effects: keep cross-tab navigation, add inline toast
  "Started — see Semantic Runs".
- Extend `semanticApi.ts` with `fetchProjectionsStatus()` typed return carrying the new
  scalar.

### Task C2: NamedGraphsPage

File: `frontend/src/pages/NamedGraphsPage.tsx`.

- Add columns: `roleInGraphSet`, `statementCount`, `latestAuditAt`, `currentStaleStatus`
  (promote stale badge to a real column).
- Add filter chips: stale/current, missing-evidence, managed/unmanaged.
- Add row actions: "Latest delta" drawer, "Dependencies" drawer.
- Wrap IRI cell in a `<CopyableIri />` (new shared component under
  `frontend/src/components/semantic/`).
- Extend `types.ts` with the new optional registry fields.

Phase C commit (after both C1 and C2 land):

```
feat(frontend): Stage 5 GraphGovernancePage tiles + NamedGraphsPage columns/filters (Stage 5 §5.1-5.2)
```

## Phase D — Frontend GraphSetPage + SemanticRunsPage (two parallel subagents)

### Task D1: GraphSetPage

File: `frontend/src/pages/GraphSetPage.tsx`.

- Add `<QueryScopeSegmentedControl />` (new shared component) with 4 scopes.
- Pass selected scope to all "Run validation/reasoning/rules" and "Export" actions.
- Add "Open SPARQL prefilled" button →
  `navigate('/?tab=semantic-import-export&graphSet={id}&prefill=sparql')`.
- Wire the attached validation reports list to the new
  `GET /validation-runs?graph_set_id=...`.

### Task D2: SemanticRunsPage

File: `frontend/src/pages/SemanticRunsPage.tsx`.

- Restructure into two panes: left `<RunHistoryTable />` (new shared component), right
  detail pane reusing existing panels.
- Add `semanticApi.fetchValidationRunList(graphSetId)`, `fetchReasoningRunList(...)`,
  `fetchRuleRunList(...)`.
- URL params: `?kind=...&run_id=...&graph_set=...`.
- Stale / superseded / current badges.
- Failed run error summary.
- Keep "Look up by run ID" as a secondary action.

Phase D commit:

```
feat(frontend): Stage 5 GraphSetPage scope control + SemanticRunsPage history (Stage 5 §5.3-5.5)
```

## Phase E — Frontend EditWorkbench + ImportExport (two parallel subagents)

### Task E1: SemanticEditWorkbenchPage

File: `frontend/src/pages/SemanticEditWorkbenchPage.tsx`.

- Wire `GraphSetSelector` into preview/apply request body.
- Mount `EvidenceBindingPanel` from Stage 4. Pass its output as `evidence_binding` on apply.
- Add `<ParseErrorBanner line column message />` (new shared component).
- Add apply button gating: `disabled = !preview.validation.conforms || preview.parse_error
  || (hasMissingEvidenceWarning && !acknowledged)`.
- Add `<AuditRecordShapeCard />` rendering the would-be audit envelope.
- Add "Run reasoning impact" optional checkbox.
- Add "stale derived results that will be created" section from
  `preview.stale_derived_pointers`.
- Add "Target graph is {editable/locked}" inline note.

### Task E2: SemanticImportExportPage

File: `frontend/src/pages/SemanticImportExportPage.tsx`.

- Build 5-step wizard: Upload → Categorize → Map IRIs → Preview delta → Validate & bind.
- Step 1 unchanged upload.
- Step 2 lists detected graph IRIs from the parsed dataset and lets the user pick a category
  for each.
- Step 3 maps IRIs to platform categories with preset rules and overrides.
- Step 4 calls `/edits` preview with `validate=false`, renders `GraphDeltaViewer`.
- Step 5 calls `/edits` preview with `validate=true`, optional OWL consistency checkbox,
  evidence binding via `EvidenceBindingPanel`, "Promote" button calls apply.
- SPARQL pane: read `?graphSet=...&prefill=sparql` URL params, seed textarea with
  `FROM NAMED <member>` clauses.
- Promote export scope selector to a segmented control matching §5.3.
- Preserve "Advanced: skip wizard" link for the legacy one-click load+apply path.

Phase E commit:

```
feat(frontend): Stage 5 EditWorkbench parse-error + ImportExport wizard (Stage 5 §5.4,5.6)
```

## Phase F — i18n + Playwright (single dispatch)

Single subagent. One commit.

### Task F1: i18n keys

Add all keys listed in spec §5.8 to `frontend/src/i18n/zh.ts` under the existing
`// Phase 8 — semantic governance` section. English source string = key, value = Chinese
translation.

### Task F2: Playwright cases

Extend `frontend/tests/semantic-governance.spec.ts` with the 12 cases listed in spec §7.3.
Use the existing `page.route('**/api/semantic/**', ...)` mock pattern.

### Task F3: Phase F commit

```
i18n(frontend): add Stage 5 keys (zh) (Stage 5 §5.8)
test(frontend): add Stage 5 Playwright coverage (Stage 5 §7.3)
```

(Two commits to match the Stage 4 convention.)

## Phase G — Verify and status flip (main agent)

### Task G1: Backend verify

```bash
cd backend && uv run pytest tests/semantic/
```

Must be green.

### Task G2: Frontend typecheck

```bash
cd frontend && npx tsc --noEmit
```

Must be green.

### Task G3: Playwright governance

```bash
cd frontend && npx playwright test semantic-governance.spec.ts
```

Must be green.

### Task G4: Spec status flip

Edit `docs/superpowers/specs/2026-07-07-semantic-stage5-governance-design.md` line 9 from
`Proposed` to `Implemented`.

### Task G5: Final commit

```
docs(semantic): Stage 5 spec and plan
```

## Self-Review Notes

### Spec Coverage Mapping

| Spec section | Plan phase |
| --- | --- |
| §4.1 Run history endpoints | A1 |
| §4.2 Projection status scalar | A2 |
| §4.3 Graph registry fields | A3 |
| §4.4 Status stale derived count | A4 |
| §4.5 Parse error structure | A5 |
| §4.6 Backend tests | B1 |
| §5.1 GraphGovernancePage | C1 |
| §5.2 NamedGraphsPage | C2 |
| §5.3 GraphSetPage | D1 |
| §5.4 SemanticEditWorkbenchPage | E1 |
| §5.5 SemanticRunsPage | D2 |
| §5.6 SemanticImportExportPage | E2 |
| §5.8 i18n | F1 |
| §7.3 Playwright | F2 |

### Type Consistency Check

- Backend schemas and frontend DTOs must stay in sync. Phase C–E subagents read the Phase A
  schema diff before writing frontend types.
- All new optional fields default to `None` on the backend and `undefined` on the frontend.

### Placeholder Scan

- The import-wizard "Advanced: skip wizard" link is the only intentional placeholder; it
  preserves the legacy one-click path and is removed in a future stage.

### Known Risks

- Run history list endpoint N+1: if the summary computes `stale_count` by walking each run,
  it can be slow on large graph sets. Mitigation: cap `limit` at 100 and document the
  cap.
- Parse error regex: rdflib's error format can vary across versions. The regex covers the
  two documented formats (`ParserError: ... at line N, col M` and `... at offset N`); other
  formats fall through to flat message.
- SPARQL prefilled `FROM NAMED` clause generation must use the actual graph member IRIs,
  not the graph set ID. The frontend reads members from `/graph-sets/{id}` and builds the
  clauses.
- Playwright mock routes must use the same URL pattern as the live API client. Verify by
  reading `semanticApi.ts` before writing mocks.
