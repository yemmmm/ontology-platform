# Semantic Stage 4 — Tools Implementation Plan

> **For agentic workers:** Pair this plan with the `superpowers:executing-plans`,
> `superpowers:test-driven-development`, and `superpowers:subagent-driven-development`
> skills. Run each phase inside a subagent and report the verify-gate command output
> back to the orchestrator.

- **Goal:** Rebuild the Stage 4 (Tools) surface — entity search, agent test, MCP catalog,
  evidence explorer, OWL consistency section — on top of the RDF canonical store and the
  existing read-model registry.
- **Architecture:** Projection-bridge (`P`) for search/agent/MCP, split (`split`) for evidence
  (K + R), `R` for knowledge conflicts folded into OWL consistency. All new read models
  dispatch through `SemanticReadModelService`; no new RDF write path; no new MCP tool.
- **Tech Stack:** Python 3 / FastAPI / Pydantic / RDFLib / Oxigraph on the backend;
  React + TypeScript + Ant Design + Playwright on the frontend; pytest for backend tests.
- **Spec:** `docs/superpowers/specs/2026-07-07-semantic-stage4-tools-design.md`

## Phase A — Backend Read Models

**Subagent:** `stage4-backend-readmodels`
**Dependencies:** none
**Verify gate:** `cd backend && uv run pytest tests/test_semantic_stage4_e2e.py tests/test_agent_test_graph_context.py -x`

### Task A1: Add the four Stage 4 templates

**Files:**
- Modify: `backend/app/services/semantic_sparql_templates.py` (extend `_TEMPLATES`)
- Reference: `backend/app/services/semantic_read_model.py:90` (composer dispatch site)

- [ ] **Step A1.1:** Add the four `ReadModelTemplate(...)` entries to `_TEMPLATES`:
  `entity-search`, `agent-test-context`, `owl-consistency-summary`, and the
  `fact-audit-queue` extension marker. Use the bodies and metadata defined in spec §4.1–§4.4.
- [ ] **Step A1.2:** Verify with `cd backend && uv run python -c "from backend.app.services.semantic_sparql_templates import get_template; [get_template(n) for n in ['entity-search','agent-test-context','owl-consistency-summary']]; print('ok')"`. Expected: prints `ok`.

### Task A2: Add the four composers

**Files:**
- Modify: `backend/app/services/semantic_read_model.py` (extend dispatch + add private
  `_compose_*` methods)
- Reference: existing `_compose_entity_shape`, `_compose_fact_audit_queue`,
  `_compose_graph_set_staleness` for the pattern

- [ ] **Step A2.1:** Add `_compose_entity_search(self, template, scope, *, q, class_iri, limit, field_set)` — runs the SPARQL body against the scope's data graph, decorates rows with the standard decorator, returns items.
- [ ] **Step A2.2:** Add `_compose_agent_test_context(self, template, scope, *, q, limit, field_set)` — thin wrapper over `_compose_entity_search` with `field_set="agent"` projection.
- [ ] **Step A2.3:** Add `_compose_owl_consistency_summary(self, template, scope, *, field_set)` — query latest `SemanticReasoningRunModel` row for the graph set with `tasks @> ["consistency"]`, project spec §4.3 fields, reuse the staleness calculator from `_compose_graph_set_staleness`.
- [ ] **Step A2.4:** Extend `_compose_fact_audit_queue` with an `evidence_bindings` projection triggered by `field_set="evidence"` — runs the SPARQL from spec §4.4 against the active data graph; returns `[]` if no `prov:wasDerivedFrom` triple exists.
- [ ] **Step A2.5:** Wire dispatch branches in `read_model()` for the four new template names alongside the existing branches.
- [ ] **Step A2.6:** Run `cd backend && uv run pytest tests/test_semantic_read_model_stage3_execution.py -x`. Expected: existing tests still pass.

### Task A3: Extend the read-model endpoint with `q` and `class_iri` params

**Files:**
- Modify: `backend/app/api/semantic.py` (the `GET /graph-sets/{gsid}/read-models/{model_name}` handler)
- Reference: spec §4.1

- [ ] **Step A3.1:** Add `q: str | None = None` and `class_iri: str | None = None` query params to the handler. Thread them into `service.read_model(...)` as kwargs.
- [ ] **Step A3.2:** Extend `SemanticReadModelService.read_model()` signature with `q` and `class_iri` keyword args; pass through to the entity-search / agent-test-context composers.
- [ ] **Step A3.3:** Verify with `cd backend && uv run pytest tests/test_semantic_stage4_e2e.py::test_read_model_entity_search -x` (test added in Task A4). Expected: PASS.

### Task A4: Stage 4 backend e2e test scaffolding

**Files:**
- Create: `backend/tests/conftest_stage4.py`
- Create: `backend/tests/test_semantic_stage4_e2e.py`
- Create: `backend/tests/test_agent_test_graph_context.py`
- Reference: `backend/tests/conftest_stage3.py`, `backend/tests/test_semantic_stage3_e2e.py`

- [ ] **Step A4.1:** Create `conftest_stage4.py` with three fixtures: `fake_graph_set_with_evidence`, `fake_store_with_prov_bindings`, `fake_reasoning_run_consistency`. Mirror the `FakeStore` pattern from `conftest_stage3.py:41+`.
- [ ] **Step A4.2:** Create `test_semantic_stage4_e2e.py` with `pytest_plugins = ("conftest_stage4",)` at the top and one test per spec §11 step that runs at the service layer:
  - `test_read_model_entity_search`
  - `test_read_model_agent_test_context`
  - `test_read_model_owl_consistency_summary`
  - `test_fact_audit_queue_evidence_bindings`
- [ ] **Step A4.3:** Create `test_agent_test_graph_context.py` covering the `AgentTestService.run_agent_test` happy path (Task B2 will need this test to land first per TDD).
- [ ] **Step A4.4:** Run `cd backend && uv run pytest tests/test_semantic_stage4_e2e.py tests/test_agent_test_graph_context.py -x`. Expected: PASS for the read-model tests, FAIL (expected) for the agent-test test until Task B2 lands.
- [ ] **Step A4.5:** Commit:
  ```bash
  git add backend/app/services/semantic_sparql_templates.py backend/app/services/semantic_read_model.py backend/app/api/semantic.py backend/tests/conftest_stage4.py backend/tests/test_semantic_stage4_e2e.py backend/tests/test_agent_test_graph_context.py && git commit -m "$(cat <<'EOF'
  feat(semantic): add Stage 4 read models (entity-search, agent-test-context, owl-consistency-summary, evidence bindings)

  Stage 4 §4.1–§4.4. Adds four templates to the read-model registry and the
  matching composers. The fact-audit-queue template gains an evidence field
  set that joins prov:wasDerivedFrom triples to evidence_chunks metadata.
  No RDF write path is introduced.
  EOF
  )"
  ```

## Phase B — Backend REST Surface and Agent-Test Refactor

**Subagent:** `stage4-backend-rest`
**Dependencies:** Phase A
**Verify gate:** `cd backend && uv run pytest tests/test_evidence_rest_surface.py tests/test_mcp_tools_endpoint.py tests/test_agent_test_graph_context.py -x`

### Task B1: Evidence-artifact REST surface

**Files:**
- Create: `backend/app/api/evidence.py` (new router)
- Modify: `backend/app/api/routes.py` (register the new router)
- Create: `backend/tests/test_evidence_rest_surface.py`
- Reference: `backend/app/repositories/models.py:159` (`EvidenceArtifactModel`),
  `:187` (`EvidenceChunkModel`)

- [ ] **Step B1.1:** Create `backend/app/api/evidence.py` with four routes:
  - `GET /api/projects/{project_id}/evidence-artifacts` — list artifacts for the project (paginated, default 50)
  - `GET /api/evidence-artifacts/{artifact_id}` — single artifact metadata (no content body)
  - `GET /api/evidence-artifacts/{artifact_id}/chunks` — list chunks ordered by `sequence`
  - `GET /api/chunks/{chunk_id}` — single chunk with text preview truncated at 500 chars
- [ ] **Step B1.2:** Register the router in `routes.py`. Use the existing SQLAlchemy session dependency pattern from `ontologies.py`.
- [ ] **Step B1.3:** Create `test_evidence_rest_surface.py` covering the four routes against an in-memory SQLite fixture seeded with one artifact + two chunks.
- [ ] **Step B1.4:** Run `cd backend && uv run pytest tests/test_evidence_rest_surface.py -x`. Expected: PASS.

### Task B2: Agent-test service refactor

**Files:**
- Modify: `backend/app/services/agent_test.py` (rewrite `run_agent_test` to call read-model)
- Modify: `backend/app/api/schemas.py` (`AgentTestResponse` schema; spec §7.2)
- Modify: `backend/app/api/agent_test.py` (no route change, just ensure the new schema is wired)
- Reference: spec §4.2

- [ ] **Step B2.1:** Add a `SemanticReadModelService` dependency to `AgentTestService.__init__`. The constructor already receives `session`, `driver`, `embedding_client`; add `read_model_service` as a fourth positional arg.
- [ ] **Step B2.2:** Rewrite `run_agent_test(...)`:
  1. Tokenize the question (split on whitespace, drop tokens ≤ 3 chars, lowercase).
  2. For each of the first 3 tokens, call `read_model_service.read_model(graph_set_id=graph_set_id, model_name="agent-test-context", q=token, limit=15)`. Union items by `iri`, keeping the highest-priority `assertion_kind` (`asserted > owl_inferred > rule_derived`).
  3. Render a human-readable context block and prepend it to the LLM prompt.
  4. Call the LLM, then return the structured `graph_context: { entries, generated_at, scope }`.
- [ ] **Step B2.3:** Update `AgentTestResponse` Pydantic schema to match spec §7.2.
- [ ] **Step B2.4:** Update `AgentTestService` factory in `backend/app/api/agent_test.py` to construct the service with the new dependency.
- [ ] **Step B2.5:** Run `cd backend && uv run pytest tests/test_agent_test_graph_context.py -x`. Expected: PASS (was FAIL after Task A4).
- [ ] **Step B2.6:** Commit:
  ```bash
  git add backend/app/api/agent_test.py backend/app/api/evidence.py backend/app/api/routes.py backend/app/api/schemas.py backend/app/services/agent_test.py backend/tests/test_evidence_rest_surface.py && git commit -m "$(cat <<'EOF'
  feat(semantic): wire agent-test to graph context read model + add evidence REST surface

  Stage 4 §4.2 and §5.1. agent-test/run now fetches structured graph
  context via the agent-test-context read model before invoking the LLM.
  Adds a minimal CRUD REST surface over evidence_artifacts/evidence_chunks
  for the file side of the EvidenceExplorer split. AgentTestResponse schema
  is updated symmetrically with the frontend.
  EOF
  )"
  ```

### Task B3: MCP tools enumeration endpoint

**Files:**
- Create: `backend/app/api/mcp_catalog.py` (new router)
- Modify: `backend/app/api/routes.py` (register)
- Create: `backend/tests/test_mcp_tools_endpoint.py`
- Reference: `backend/app/mcp/server.py`, `backend/app/mcp/tools/__init__.py`

- [ ] **Step B3.1:** Add `GET /api/mcp/tools` that introspects the FastMCP registry. The handler:
  1. Iterates `mcp._tool_manager.list_tools()` (or the FastMCP-version-appropriate equivalent).
  2. For each tool, extracts `{name, description, input_schema_summary, source_file, category}`.
  3. Buckets `category` by source filename: `system`, `interview`, `semantic`.
- [ ] **Step B3.2:** Register the router in `routes.py`.
- [ ] **Step B3.3:** Create `test_mcp_tools_endpoint.py` asserting the response includes ≥ 30 tools, includes `compile_and_apply_canonical_command`, and has all three categories.
- [ ] **Step B3.4:** Run `cd backend && uv run pytest tests/test_mcp_tools_endpoint.py -x`. Expected: PASS.
- [ ] **Step B3.5:** Commit:
  ```bash
  git add backend/app/api/mcp_catalog.py backend/app/api/routes.py backend/tests/test_mcp_tools_endpoint.py && git commit -m "$(cat <<'EOF'
  feat(mcp): add /api/mcp/tools enumeration endpoint

  Stage 4 §5.4. Introspects the FastMCP tool registry and returns
  {name, description, input_schema_summary, source_file, category} for
  each registered tool. Category is bucketed by the source filename
  (system / interview / semantic).
  EOF
  )"
  ```

## Phase C1 — Frontend EntitiesSearchPage

**Subagent:** `stage4-frontend-search`
**Dependencies:** Phase A
**Verify gate:** `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Search`

### Task C1.1: Create `EntitiesSearchPage.tsx`

**Files:**
- Create: `frontend/src/pages/EntitiesSearchPage.tsx`
- Reference: `frontend/src/pages/EntitiesPage.tsx` for prop shape and styling patterns,
  `frontend/src/semanticApi.ts:370` for `readModel` helper

- [ ] **Step C1.1.1:** Build the page per spec §7.1 ASCII mock. Props: `{ graphSetId, ontologyId, readOnly, request }`.
- [ ] **Step C1.1.2:** Implement `useEntitiesSearch(request, graphSetId)` hook with debounced (200ms) input, scope filter state, and class filter state.
- [ ] **Step C1.1.3:** Render results with `assertion_kind` chip and stale warning per row.
- [ ] **Step C1.1.4:** Add Playwright test coverage to `stage4-tools.spec.ts` (Task F).
- [ ] **Step C1.1.5:** Commit:
  ```bash
  git add frontend/src/pages/EntitiesSearchPage.tsx && git commit -m "feat(frontend): add EntitiesSearchPage (Stage 4 §7.1)

  Stage 4 §7.1. Adds a new Tools-stage page that searches entities across
  the active graph set through the new entity-search read model. Results
  carry AssertionKind, source graph IRI, and staleness state."
  ```

### Task C1.2: Wire `EntitiesSearchPage` into `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx` (WorkspaceTab + WorkspaceContent branches)
- Reference: spec §7.3

- [ ] **Step C1.2.1:** Add `"search"` to the `WorkspaceTab` union type and add a row to `workspaceTabs` under the `tools` stage with the `Search` icon (re-import `Search` from lucide-react — it was removed from the import block in Stage 3).
- [ ] **Step C1.2.2:** Add a `WorkspaceContent` branch for `props.tab === "search"` that requires a `graphSet` query param and renders `<EntitiesSearchPage ... />`.
- [ ] **Step C1.2.3:** Verify with `cd frontend && pnpm tsc --noEmit`. Expected: PASS.
- [ ] **Step C1.2.4:** Commit:
  ```bash
  git add frontend/src/App.tsx && git commit -m "feat(frontend): wire EntitiesSearchPage into Tools stage nav (Stage 4 §7.3)"
  ```

## Phase C2 — Frontend AgentTestPage Rewrite

**Subagent:** `stage4-frontend-agent`
**Dependencies:** Phase A, Phase B
**Verify gate:** `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Agent`

### Task C2.1: Extract and rewrite `AgentTestPage`

**Files:**
- Create: `frontend/src/pages/AgentTestPage.tsx`
- Modify: `frontend/src/App.tsx` (remove the inline `AgentTestPage` function at lines 926-982)
- Modify: `frontend/src/types.ts` (update `AgentTestResponse` and add `AgentTestGraphContextEntry` per spec §7.2)
- Reference: spec §7.2 ASCII mock

- [ ] **Step C2.1.1:** Update `types.ts` to add `AgentTestGraphContextEntry` and restructure `AgentTestResponse.graph_context` per spec §7.2.
- [ ] **Step C2.1.2:** Build `frontend/src/pages/AgentTestPage.tsx` rendering: question textarea, answer panel, structured graph context (with AssertionKind chips and stale warnings), tool calls timeline, prompt preview, warnings, errors.
- [ ] **Step C2.1.3:** Replace the inline function in `App.tsx` with `<AgentTestPage ontology={...} request={...} mutate={...} graphSetId={queryValue("graphSet")} />`. Update the `WorkspaceContent` branch to pass `graphSetId`.
- [ ] **Step C2.1.4:** Verify with `cd frontend && pnpm tsc --noEmit`. Expected: PASS.
- [ ] **Step C2.1.5:** Commit:
  ```bash
  git add frontend/src/pages/AgentTestPage.tsx frontend/src/App.tsx frontend/src/types.ts && git commit -m "feat(frontend): rewrite AgentTestPage to consume structured graph context (Stage 4 §7.2)"
  ```

## Phase C3 — Frontend McpToolsPage Rewrite

**Subagent:** `stage4-frontend-mcp`
**Dependencies:** Phase B
**Verify gate:** `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools MCP`

### Task C3.1: Extract and rewrite `McpToolsPage`

**Files:**
- Create: `frontend/src/pages/McpToolsPage.tsx`
- Modify: `frontend/src/App.tsx` (remove the inline `McpToolsPage` function at lines 984-1011)
- Reference: spec §7.3

- [ ] **Step C3.1.1:** Build `McpToolsPage.tsx` that:
  1. Fetches `GET /api/mcp/tools` via `useEffect`.
  2. Buckets tools by `category` (`system`, `interview`, `semantic`).
  3. Renders one panel per category with a tool row per item (name + description + source-file badge).
- [ ] **Step C3.1.2:** Replace the inline function in `App.tsx` with `<McpToolsPage request={governedRequest} />`.
- [ ] **Step C3.1.3:** Verify with `cd frontend && pnpm tsc --noEmit`. Expected: PASS.
- [ ] **Step C3.1.4:** Commit:
  ```bash
  git add frontend/src/pages/McpToolsPage.tsx frontend/src/App.tsx && git commit -m "feat(frontend): rewrite McpToolsPage to fetch /api/mcp/tools (Stage 4 §7.3)"
  ```

## Phase D1 — Frontend EvidenceExplorer Panel

**Subagent:** `stage4-frontend-evidence`
**Dependencies:** Phase A, Phase B
**Verify gate:** `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Evidence`

### Task D1.1: Build `EvidenceExplorerPanel`

**Files:**
- Create: `frontend/src/components/semantic/EvidenceExplorerPanel.tsx`
- Modify: `frontend/src/pages/FactAuditPage.tsx` (mount the panel in a side drawer)
- Reference: `frontend/src/components/semantic/EvidenceBindingPanel.tsx` for visual style;
  spec §4.4 for the data contract

- [ ] **Step D1.1.1:** Build `EvidenceExplorerPanel` that accepts `bindings: EvidenceBinding[]` and `request: WorkbenchRequest`. Renders one row per binding: `document_filename`, `sequence`, `text_preview`, `char_start–char_end`.
- [ ] **Step D1.1.2:** If `bindings` is empty, render the existing `EvidenceBindingPanel` (Stage 1) inside the same drawer so users can still mark a fact as `missing_evidence`.
- [ ] **Step D1.1.3:** Modify `FactAuditPage` to:
  1. Fetch `fact-audit-queue` with `field_set="evidence"` (when the drawer is open for a fact).
  2. Render the `EvidenceExplorerPanel` inside the existing review modal or a new side drawer.
- [ ] **Step D1.1.4:** Define `EvidenceBinding` TypeScript type in `frontend/src/types.ts`.
- [ ] **Step D1.1.5:** Verify with `cd frontend && pnpm tsc --noEmit`. Expected: PASS.
- [ ] **Step D1.1.6:** Commit:
  ```bash
  git add frontend/src/components/semantic/EvidenceExplorerPanel.tsx frontend/src/pages/FactAuditPage.tsx frontend/src/types.ts && git commit -m "feat(frontend): mount EvidenceExplorerPanel inside FactAuditPage drawer (Stage 4 §4.4)"
  ```

## Phase D2 — Frontend OWL Consistency Section

**Subagent:** `stage4-frontend-consistency`
**Dependencies:** Phase A
**Verify gate:** `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Consistency`

### Task D2.1: Add OWL Consistency section to `GraphGovernancePage`

**Files:**
- Modify: `frontend/src/pages/GraphGovernancePage.tsx`
- Reference: spec §4.3

- [ ] **Step D2.1.1:** Add a new panel "OWL Consistency" between the existing graph-set list and the audits section. The panel:
  1. Fetches `GET /api/semantic/graph-sets/{activeGraphSetId}/read-models/owl-consistency-summary`.
  2. Renders `consistent`, `classification`, `entailment_count`, `unsatisfiable_classes`, `result_graph_iri`, `started_at`, `finished_at`, `is_stale`.
  3. Shows a stale warning banner if `is_stale === true`.
- [ ] **Step D2.1.2:** Wire the panel into the existing layout. No new tab.
- [ ] **Step D2.1.3:** Verify with `cd frontend && pnpm tsc --noEmit`. Expected: PASS.
- [ ] **Step D2.1.4:** Commit:
  ```bash
  git add frontend/src/pages/GraphGovernancePage.tsx && git commit -m "feat(frontend): add OWL Consistency section to GraphGovernancePage (Stage 4 §4.3)"
  ```

## Phase E — Cleanup Sweep and i18n

**Subagent:** `stage4-frontend-cleanup`
**Dependencies:** C1, C2, C3, D1, D2
**Verify gate:** `cd frontend && pnpm tsc --noEmit && pnpm test`

### Task E1: Remove dead code

**Files:**
- Modify: `frontend/src/types.ts` (remove `EntitySearchResult` at lines 198-204)
- Modify: `frontend/src/styles.css` (remove `.entitySearchPage` selectors at lines ~1873, ~2140)
- Reference: spec §6.1

- [ ] **Step E1.1:** Grep for `EntitySearchResult` callers; if zero, delete the type.
- [ ] **Step E1.2:** Grep for `.entitySearchPage` CSS references; if zero, delete the selectors.
- [ ] **Step E1.3:** Run `cd frontend && pnpm tsc --noEmit`. Expected: PASS.
- [ ] **Step E1.4:** Commit:
  ```bash
  git add frontend/src/types.ts frontend/src/styles.css && git commit -m "chore(frontend): drop dead EntitySearchResult type and entitySearchPage CSS (Stage 4 §6.1)"
  ```

### Task E2: i18n keys

**Files:**
- Modify: `frontend/src/i18n/translations.ts` (extend both `zh` and `en` maps)
- Reference: spec §7.4

- [ ] **Step E2.1:** Audit new copy added by Phases C1–D2. For every literal string, add a translation key to both `zh` and `en` maps.
- [ ] **Step E2.2:** Run `cd frontend && pnpm tsc --noEmit && pnpm test`. Expected: PASS.
- [ ] **Step E2.3:** Commit:
  ```bash
  git add frontend/src/i18n/translations.ts && git commit -m "i18n(frontend): add Stage 4 keys (zh + en) (Stage 4 §7.4)"
  ```

## Phase F — Playwright E2E

**Subagent:** `stage4-e2e`
**Dependencies:** Phase E
**Verify gate:** `cd frontend && pnpm test stage4-tools`

### Task F1: Add `stage4-tools.spec.ts`

**Files:**
- Create: `frontend/tests/stage4-tools.spec.ts`
- Modify: `frontend/tests/stage3-publish.spec.ts` if its `mockCommon` catch-all needs to branch on Stage 4 endpoints
- Reference: `frontend/tests/stage3-publish.spec.ts` for the mock-and-fixture pattern

- [ ] **Step F1.1:** Add a `mockStage4(page, mode)` helper with three modes: `success`, `empty`, `failFirst`. Cover all Stage 4 endpoints:
  - `GET /api/semantic/graph-sets/{gsid}/read-models/entity-search`
  - `GET /api/semantic/graph-sets/{gsid}/read-models/agent-test-context`
  - `POST /api/agent-test/run`
  - `GET /api/mcp/tools`
  - `GET /api/projects/{pid}/evidence-artifacts`
  - `GET /api/evidence-artifacts/{id}/chunks`
  - `GET /api/semantic/graph-sets/{gsid}/read-models/owl-consistency-summary`
  - `GET /api/semantic/graph-sets/{gsid}/read-models/fact-audit-queue` (extend the existing mock)
- [ ] **Step F1.2:** Write one Playwright test per spec §11 step (eight tests total). Use data-attr selectors instead of locale-sensitive text (Stage 3 review-fix lesson).
- [ ] **Step F1.3:** Run `cd frontend && pnpm test stage4-tools`. Expected: PASS.
- [ ] **Step F1.4:** Commit:
  ```bash
  git add frontend/tests/stage4-tools.spec.ts frontend/tests/stage3-publish.spec.ts && git commit -m "test(frontend): add Stage 4 Playwright coverage (Stage 4 §11)"
  ```

## Phase G — Cleanup and Status Flip

**Subagent:** `stage4-cleanup`
**Dependencies:** Phase F
**Verify gate:** `git log --oneline -20 | grep "Stage 4"`

### Task G1: Final cleanup sweep

**Files:**
- Audit: any leftover dead imports, unused fixtures, TODO comments introduced during Stage 4.

- [ ] **Step G1.1:** Run `cd backend && uv run pytest`. Expected: full suite PASS.
- [ ] **Step G1.2:** Run `cd frontend && pnpm tsc --noEmit && pnpm test`. Expected: full suite PASS.
- [ ] **Step G1.3:** Address any review-fix items found by the orchestrator during Phase F. Use the `(Phase F review fix)` commit suffix convention.
- [ ] **Step G1.4:** Commit any cleanup as `chore(semantic): Stage 4 final cleanup sweep (Phase G)`.

### Task G2: Mark spec as implemented

**Files:**
- Modify: `docs/superpowers/specs/2026-07-07-semantic-stage4-tools-design.md`

- [ ] **Step G2.1:** Flip `**Status:** Draft` to `**Status:** Implemented`.
- [ ] **Step G2.2:** Commit:
  ```bash
  git add docs/superpowers/specs/2026-07-07-semantic-stage4-tools-design.md && git commit -m "docs(semantic): mark Stage 4 spec as implemented"
  ```

## Self-Review Notes

### Spec Coverage Mapping

| Phase | Spec section |
| --- | --- |
| A | §3.1, §4.1, §4.2, §4.3, §4.4 |
| B | §3.3, §3.4, §3.5, §4.2 (write side), §5.1, §5.4 |
| C1 | §4.1, §7.1, §7.3 |
| C2 | §4.2, §7.2, §7.3 |
| C3 | §5.4, §7.3 |
| D1 | §3.3, §4.4 |
| D2 | §3.5, §4.3 |
| E | §6.1, §7.4 |
| F | §9.2, §11 |
| G | §1, §10.1 |

### Type Consistency Check

- `AgentTestResponse` Pydantic schema (B2) ↔ TypeScript type (C2.1.1) — symmetric update.
- `EvidenceBinding` TypeScript type (D1.1.4) ↔ `fact-audit-queue` evidence field set composer (A2.4) — field names match the spec §4.4 table.
- `McpTool` response from `/api/mcp/tools` (B3.1) ↔ McpToolsPage renderer (C3.1.1) — field names match the spec §5.4 bullet list.

### Placeholder Scan

- Phase A's four templates and composers are fully specified in spec §4 — no `# Composer-driven` placeholder should leak past Phase A's verify gate.
- No `TODO: Stage 4` or `pending Stage 4` strings should remain after Phase E.

### Known Risks

- **`FastMCP._tool_manager` API stability.** Phase B3 depends on the FastMCP-version-appropriate way to enumerate tools. If the API surface is unstable, the fallback is to iterate the source files in `backend/app/mcp/tools/` and parse the `@server.tool()` decorators statically. The Phase B3 task description calls this out.
- **`agent-test-context` keyword extraction for CJK.** The naive tokenizer is wrong for CJK input. The Stage 4 e2e only covers English; a CJK fixture is deferred.
- **`prov:wasDerivedFrom` IRI convention drift.** If Phase 2 namespace mapping has moved since the spec was written, the composer fails open. The Stage 4 e2e must seed a fixture that uses the documented IRI form to catch this drift early.
