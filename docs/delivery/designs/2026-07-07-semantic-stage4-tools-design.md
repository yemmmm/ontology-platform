# Semantic Stage 4 — Tools Design

- **Date:** 2026-07-07
- **Scope driver:** `docs/architecture/semantic/functional-semantic-load-inventory.md` Stage 4 — Tools
- **Architecture approach:** Projection-bridge (`P`) for search/agent/MCP, split (`split`) for
  evidence (file/chunks `K` + evidence→fact binding `R`), `R` for knowledge-conflicts folded
  into the OWL consistency read model.
- **Status:** Implemented

## 1. Goal and Non-Goals

### Goals

1. Replace the hard-coded `McpToolsPage` with a runtime catalog served from the FastMCP tool
   registry so that the UI is always in sync with the registered tools.
2. Rebuild `AgentTestPage` so the question run reads from the graph set via a dedicated read
   model before invoking the LLM; surface `AssertionKind`, `source_graph_iri`, and provenance
   on every returned context entry.
3. Introduce `EntitiesSearchPage` as a graph-derived search surface that returns entities with
   `AssertionKind`, graph IRI, graph-set id, staleness state, and evidence status — read through
   a new read model rather than a free-standing search backend.
4. Provide a minimal Postgres REST surface (`/projects/{id}/evidence-artifacts`,
   `/evidence-artifacts/{id}/chunks`, `/chunks/{id}`) so the file/chunk side of evidence
   browsing has an operational source of truth (Keep side of the `split`).
5. Build the evidence→fact binding side of the `split` (`R`) by reading
   `prov:wasDerivedFrom` triples in `graph/data` and exposing them through an extended
   `fact-audit-queue` field set.
6. Fold the legacy `knowledge-conflicts` concept into a new `owl-consistency-summary` read model
   and render its summary as a section of the governance dashboard — no new conflict table.

### Non-Goals

- No rebuild of the underlying EvidenceArtifact/EvidenceChunk Postgres storage; those tables
  (`evidence_artifacts`, `evidence_chunks`) are kept as the operational source of truth.
- No new SHACL or OWL editor. The Stage 4 surface only *consumes* existing consistency
  reasoning output, it does not author new ontology constraints.
- No new top-level navigation stage. All Stage 4 work stays inside the existing five stages
  (`intake`, `knowledge`, `publish`, `tools`, `governance`); the evidence explorer is mounted
  as a sub-panel of `FactAuditPage`, and the OWL consistency panel is mounted inside
  `GraphGovernancePage`.
- No legacy `/entities/search`, `/ontologies/{id}/entities/search`,
   `/ontologies/{id}/knowledge-conflicts`, or `/conflicts/{id}/resolve` routes are re-created.
   Stage 3 hard-cut already removed them; this stage does not reverse that.
- No new MCP tool registration. Stage 4 only *enumerates* the existing registered tools for
  display; it does not add, remove, or rename any tool.

## 2. Locked-In Decisions

| Decision | Resolution | Source |
| --- | --- | --- |
| Entity search backend | Reuse `SemanticReadModelService` with a new SPARQL-driven template `entity-search`. No standalone search service. | Inventory Stage 4 row 1 (P); this spec §4.1 |
| Agent context fetch | Pre-LLM graph retrieval via a new read-model template `agent-test-context`. Same envelope shape as other read models. | Inventory Stage 4 row 2 (P); this spec §4.2 |
| Evidence operational REST | Minimal CRUD endpoints over the existing `EvidenceArtifactModel` / `EvidenceChunkModel`. No new repository abstraction. | Inventory Stage 4 row 3 (split, K); this spec §5.1 |
| Evidence→fact binding | Read `prov:wasDerivedFrom` triples in `graph/data/{id}`; expose through the `fact-audit-queue` read model under a new `detail` field set. | Inventory Stage 4 row 3 (split, R); this spec §4.4 |
| MCP catalog endpoint | New `GET /api/mcp/tools` that introspects `FastMCP`'s tool registry through `_tool_manager.list_tools()`. | Inventory Stage 4 row 4 (P); this spec §5.4 |
| Knowledge conflicts | No new conflict schema. Reuse `reasoning-runs` (task `consistency`) output surfaced via a new composer `owl-consistency-summary`. | Inventory Stage 4 row 6 (R); this spec §4.3 |
| Workspace tab placement | Add a new `WorkspaceTab = "search"` under the existing `tools` stage. `agent-test`, `mcp-tools`, `setting` tabs unchanged. | This spec §7.3 |
| Routing param for evidence drawer | Use `?evidence=<chunk_iri>` URL parameter, mirroring the existing `?graph=...`, `?graphSet=...` pattern. | Existing `App.tsx` query-string discipline |

## 3. Shared Foundations

### 3.1 `SemanticReadModelService`

The Stage 4 read models are registered through the same dispatch surface used by Stages 2–3:

- Template table at `backend/app/services/semantic_sparql_templates.py:_TEMPLATES`.
- Composer dispatch at `backend/app/services/semantic_read_model.py:SemanticReadModelService.read_model`.
- Endpoint surface `GET /api/semantic/graph-sets/{graph_set_id}/read-models/{model_name}` at
  `backend/app/api/semantic.py` (around line 1175).

Stage 4 adds four entries to this registry and does not change the dispatch protocol.

### 3.2 `compile_and_apply_canonical_command`

Evidence→fact bindings (the `R` half of `EvidenceExplorer`) are written by `prov:wasDerivedFrom`
triples that already land in `graph/data/{id}` through canonical-write `submit_semantic_edit`
calls. The Stage 4 surface is **read-only** on this binding; no new write path is introduced.
Writers are unchanged from `backend/app/services/semantic_canonical_write.py`.

### 3.3 `EvidenceArtifactModel` / `EvidenceChunkModel`

Tables at `backend/app/repositories/models.py:159` and `:187` already store the operational
file/chunk data. Stage 4 introduces REST routes over them but does not alter the schema.

### 3.4 `FastMCP` tool registry

`backend/app/mcp/server.py:1-19` constructs `FastMCP("ontology-platform")` and calls
`register_all(mcp)` from `backend/app/mcp/tools/__init__.py:24-29`. Each registered tool is
introspectable through the underlying `_tool_manager` attribute. Stage 4 exposes this registry
through a new HTTP route.

### 3.5 Reasoning run consistency output

`SemanticReasoningRunResponse` at `backend/app/api/schemas.py:209-216` already carries
`consistent: bool | None`, `classification`, `entailments`, and `result_graph_iri`. Stage 4
consumes this through a composer that reads the latest reasoning-run row for a graph set.

## 4. Read-Model Contracts (New)

All four templates below extend `_TEMPLATES` and dispatch through `SemanticReadModelService`.
Envelope shape is unchanged: `{ graph_set_id, model_name, projection_version, items: [...] }`.

### 4.1 `entity-search` (P)

`ReadModelTemplate(name="entity-search", projection_version=1, required_roles=["reader"],
needs_reasoning=False, needs_rules=False, default_limit=50, assertion_kind="any",
evidence_status="any", primary_iri_variable="entity")`.

| Field | Type | Source |
| --- | --- | --- |
| `iri` | string | `?entity` (graph/data + ontology graph) |
| `label` | string \| null | `rdfs:label` literal |
| `comment` | string \| null | `rdfs:comment` literal |
| `class_iri` | string \| null | `rdf:type`/`owl:Class` join |
| `class_label` | string \| null | `rdfs:label` of class |
| `assertion_kind` | `"asserted" \| "owl_inferred" \| "rule_derived"` | decorator (see §3.1) |
| `source_graph_iri` | string | decorator |
| `source_signature` | string \| null | decorator |
| `evidence_status` | string | decorator |
| `is_stale` | bool | decorator |
| `graph_set_id` | string | decorator |

Body (SPARQL, executed against the active scope):

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT DISTINCT ?entity ?label ?comment ?class ?class_label WHERE {
  ?entity a ?class .
  ?class a rdfs:Class .
  OPTIONAL { ?entity rdfs:label ?label . }
  OPTIONAL { ?entity rdfs:comment ?comment . }
  OPTIONAL { ?class rdfs:label ?class_label . }
  FILTER(
    CONTAINS(LCASE(COALESCE(STR(?label), "")), LCASE(?q)) ||
    CONTAINS(LCASE(COALESCE(STR(?comment), "")), LCASE(?q)) ||
    CONTAINS(LCASE(STR(?entity)), LCASE(?q))
  )
}
ORDER BY LCASE(?label)
LIMIT {limit}
```

The `q` and `class_iri` query parameters are bound by the composer before the SPARQL string is
handed to the store (mirrors the existing `entity-shape` composer pattern at
`semantic_read_model.py:90`).

Implementation:

- Add `_entity_search_compose(body, scope, *, q, class_iri, limit, field_set)` helper alongside
  `_compose_entity_shape` in `semantic_read_model.py`.
- Dispatch entry in `read_model()`:
  ```python
  elif template.name == "entity-search":
      items = self._compose_entity_search(template, scope, q=q, class_iri=class_iri,
                                          limit=limit, field_set=field_set)
  ```
- Endpoint exposure: extend the existing `GET /graph-sets/{gsid}/read-models/{model_name}`
  handler to accept `?q=...` and `?class_iri=...`. The two new query params propagate into
  `read_model()` as keyword arguments.

### 4.2 `agent-test-context` (P)

`ReadModelTemplate(name="agent-test-context", projection_version=1, required_roles=["reader"],
needs_reasoning=True, needs_rules=False, default_limit=15, assertion_kind="any",
evidence_status="any", primary_iri_variable="entity")`.

| Field | Type | Source |
| --- | --- | --- |
| `iri` | string | `?entity` |
| `label` | string \| null | rdfs:label |
| `class_label` | string \| null | rdfs:label of `rdf:type` |
| `assertion_kind` | enum | decorator |
| `source_graph_iri` | string | decorator |
| `source_signature` | string \| null | decorator |
| `provenance` | object | decorator (same shape used in Stage 2 §3.2) |

Body: same SPARQL skeleton as `entity-search` minus the `comment` projection, with the limit
defaulting to 15. Composer reuses `_compose_entity_search` with `field_set="agent"`.

The `AgentTestService.run_agent_test` flow becomes:

1. Tokenize the question into 1–3 keywords (lowercase, strip stopwords ≤ 3 chars).
2. For each keyword, call `read_model(graph_set_id, "agent-test-context", q=kw, limit=15)`.
   Union the items by `iri`, keeping the highest-priority `assertion_kind`
   (`asserted > owl_inferred > rule_derived`).
3. Build a structured `graph_context: { entries: [...items], generated_at, scope }` and feed
   the human-readable rendering into the LLM prompt.
4. Return the structured object on `AgentTestResponse.graph_context` (replacing the current
   opaque `JsonObject`).

### 4.3 `owl-consistency-summary` (R)

`ReadModelTemplate(name="owl-consistency-summary", projection_version=1,
required_roles=["reader"], needs_reasoning=True, needs_rules=False, default_limit=1,
assertion_kind="owl_inferred", evidence_status="any", primary_iri_variable="run")`.

Composer-driven (no body SPARQL). The composer queries the latest
`SemanticReasoningRunModel` row for the graph set (filtered by `tasks @> ["consistency"]`) and
shapes the result:

| Field | Type | Source |
| --- | --- | --- |
| `run_id` | string | `reasoning_runs.id` |
| `consistent` | bool \| null | `reasoning_runs.consistent` |
| `classification` | string \| null | `reasoning_runs.classification` |
| `entailment_count` | int | `length(reasoning_runs.entailments)` |
| `unsatisfiable_classes` | string[] | `entailments` parse, filter by class pattern |
| `result_graph_iri` | string | `reasoning_runs.result_graph_iri` |
| `started_at` | ISO 8601 | `reasoning_runs.started_at` |
| `finished_at` | ISO 8601 \| null | `reasoning_runs.finished_at` |
| `is_stale` | bool | True if any member graph has been edited since `finished_at` |

`is_stale` reuses the staleness calculator introduced in Stage 3 (`_compose_graph_set_staleness`)
so that the governance dashboard can flag when the consistency result pre-dates a recent edit.

Composer entry point: `_compose_owl_consistency_summary(template, scope, field_set)`.

### 4.4 `fact-audit-queue` extension — `evidence_bindings` field set (R)

The existing `fact-audit-queue` template (Stage 2 §4.4) is extended with an optional
`field_set="evidence"` composer path:

| Field | Type | Source |
| --- | --- | --- |
| (existing fields) | … | unchanged |
| `evidence_bindings` | `[{ chunk_iri, document_iri, document_filename, sequence, char_start, char_end, text_preview }]` | SPARQL `prov:wasDerivedFrom` lookup against `graph/data/{id}` joined to `evidence_chunks` via IRI convention |

Composer logic (`_compose_fact_audit_queue` extension):

```sparql
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?chunk ?doc ?sequence ?char_start ?char_end ?text WHERE {
  ?fact prov:wasDerivedFrom ?chunk .
  ?chunk a <tag:ontology-platform.internal,2026:EvidenceChunk> ;
         <tag:ontology-platform.internal,2026:sourceDocument> ?doc ;
         <tag:ontology-platform.internal,2026:sequence> ?sequence ;
         <tag:ontology-platform.internal,2026:charStart> ?char_start ;
         <tag:ontology-platform.internal,2026:charEnd> ?char_end ;
         <tag:ontology-platform.internal,2026:text> ?text .
}
```

The composer then joins `?doc` to `evidence_artifacts.filename` through the
`tag:ontology-platform.internal,2026:` IRI convention used by Phase 2 namespace mapping.
Chunk IRIs use the form
`tag:ontology-platform.internal,2026:evidence/{doc_id}/{sequence}`.

If no `prov:wasDerivedFrom` triple exists for a fact, `evidence_bindings` is `[]`. The Stage 4
surface treats empty bindings identically to `evidence_status="missing_evidence"` for display
purposes — it does not write a binding; canonical-write flow remains the only writer.

## 5. Canonical Writes

Stage 4 introduces no new canonical-write command. All RDF writes that surface in Stage 4
read models continue to flow through:

- `submit_semantic_edit` (for `prov:wasDerivedFrom` triples landing in `graph/data/{id}`)
- `run_semantic_reasoning` (for `consistent` / `entailments` fields in `owl-consistency-summary`)

The Stage 4 endpoints under `/projects/{id}/evidence-artifacts` write Postgres only and never
touch the RDF store.

## 6. Backend Hard-Cut Removals

Stage 3 already removed every legacy endpoint in the Stage 4 inventory (no `/entities/search`,
no `/ontologies/{id}/knowledge-conflicts`, no `/conflicts/{id}/resolve`, no
`/ontologies/{id}/entities/search`). Stage 4 only needs to remove **dead frontend type
residue** introduced before the Stage 3 cut:

### 6.1 Frontend Files

- `frontend/src/types.ts:198-204` — `EntitySearchResult` type alias is unused (no caller in
  the codebase). Removed; superseded by the new read-model envelope.
- `frontend/src/styles.css` lines containing `.entitySearchPage` class selectors (lines around
  1873, 2140 per inventory audit) — removed; replaced by the new page styles.

### 6.2 Backend Files

- `backend/app/services/semantic_search_projection.py:96-100` — the `assertion_kind="unknown"`
  default is replaced with `"asserted"` to match the Stage 2 §3.2 decorator contract. This is
  a one-line fix, not a hard-cut.

### 6.3 Models / Migrations

None. No table is added, dropped, or renamed.

### 6.4 MCP Tools

None. No MCP tool is added or removed.

## 7. Frontend Rebuilds

### 7.1 `EntitiesSearchPage` (new page)

**File:** `frontend/src/pages/EntitiesSearchPage.tsx` (new).

```
┌──────────────────────────────────────────────────────────────┐
│  [ Search entities across the active graph set          ] 🔍 │
│  Filter: [ All classes ▾ ]   Scope: [ Asserted ▾ ]           │
├──────────────────────────────────────────────────────────────┤
│  N results · sorted by label                                 │
├──────────────────────────────────────────────────────────────┤
│  ◯ Acme Corp                  [asserted]  graph:data/{gsid}  │
│    Class: Organization                                        │
│    "Acme is a manufacturer of widgets..."                     │
│  ◯ Widget A                    [owl_inferred] ⚠ stale         │
│    Class: Product                                             │
└──────────────────────────────────────────────────────────────┘
```

**Hooks:** `useEntitiesSearch(request, graphSetId)` (new) wraps `readModel` with query/state
machinery — debounced search input, class filter, scope filter
(`asserted`/`owl_inferred`/`rule_derived`/`all`).

**Action semantics:** clicking a row opens the existing `EntitiesPage` in a side panel via
`navigateWorkspace("entities", { graphSet, entity })`. The page itself performs no writes.

### 7.2 `AgentTestPage` rewrite (existing inline component extracted)

**File:** `frontend/src/pages/AgentTestPage.tsx` (new file, replacing the inline
implementation in `App.tsx:926-982`).

```
┌──────────────────────────────────────────────────────────────┐
│  Question:  [ Ask a question against the active graph set ]   │
│                                                              │
│  Answer                                                      │
│  ───────                                                     │
│  Acme Corp is an organization that...                        │
│                                                              │
│  Graph context (N entries)                                   │
│  ────────────────────────                                    │
│  • Acme Corp                  [asserted]    graph:data/{gs}  │
│  • Widget A                    [owl_inferred] ⚠ stale        │
│                                                              │
│  Tool calls │ Prompt preview │ Warnings │ Errors             │
└──────────────────────────────────────────────────────────────┘
```

**Hooks:** `useAgentTest(request, ontology, graphSetId)` (new) wraps the run endpoint and
surfaces the structured `graph_context.entries` for inline rendering.

**`AgentTestResponse` schema update** at `frontend/src/types.ts:278-285`:

```ts
export type AgentTestGraphContextEntry = {
  iri: string;
  label: string | null;
  class_label: string | null;
  assertion_kind: "asserted" | "owl_inferred" | "rule_derived";
  source_graph_iri: string;
  source_signature: string | null;
  is_stale: boolean;
};

export type AgentTestResponse = {
  answer: string;
  tool_calls: JsonObject[];
  graph_context: {
    entries: AgentTestGraphContextEntry[];
    generated_at: string;
    scope: { graph_set_id: string; ontology_id: string };
  };
  prompt_preview: string;
  warnings: string[];
  errors: string[];
};
```

The backend `AgentTestResponse` Pydantic schema is updated symmetrically.

### 7.3 Routing and Navigation

`WorkspaceTab` gains a new variant `"search"` placed under the `tools` stage:

```ts
{ id: "search", stage: "tools", label: "Search", detail: "Graph entity search",
  icon: Search },
```

The `App.tsx` `WorkspaceContent` switch adds a branch:

```tsx
if (props.tab === "search") {
  const graphSetId = queryValue("graphSet");
  if (!graphSetId) return <EmptyState ... />;  // require a graph set
  return <EntitiesSearchPage graphSetId={graphSetId} ontologyId={props.ontology.id}
                             readOnly={readOnly} request={governedRequest} />;
}
```

`stageDefaultTab.tools` stays as `"agent-test"`; the Tools stage shows four tabs in order:
`agent-test`, `search`, `mcp-tools`, `setting`.

### 7.4 i18n

Stage 4 adds new translation keys under both `zh` and `en` in
`frontend/src/i18n/translations.ts`. Keys cover: tab labels, panel titles, scope filter
options, AssertionKind chips, stale warnings, evidence drawer copy, MCP catalog categories.

## 8. Error Handling

| Scenario | UX |
| --- | --- |
| `entity-search` returns zero rows | Inline empty state with search input preserved; suggest trying a broader query |
| `entity-search` SPARQL execution fails | Banner with backend error message; retry button; results area blanked |
| `agent-test-context` returns zero entries | LLM is still called with an explicit "no graph context" preamble; the run completes with `graph_context.entries: []` and a `warnings: ["No graph context matched the question."]` entry |
| LLM call fails | `errors` field populated; `answer` empty; `graph_context` still returned so the user can see what was retrieved |
| `/api/mcp/tools` fails | Page renders an inline error banner; no retry loop |
| `/api/projects/{pid}/evidence-artifacts` returns 404 | Fact audit drawer shows "Evidence source documents not yet uploaded for this project" |
| `prov:wasDerivedFrom` triple missing for a fact | Drawer shows "No evidence binding for this fact" with the existing `EvidenceBindingPanel` (Stage 1) bound to `evidence_status="missing_evidence"` |

## 9. Testing Strategy

### 9.1 Backend

**New files:**

- `backend/tests/test_semantic_stage4_e2e.py` — happy-path Stage 4 e2e mirroring the Stage 3
  service-layer test pattern (direct composer/service calls, no HTTP).
- `backend/tests/conftest_stage4.py` — fixtures: `fake_graph_set_with_evidence`,
  `fake_store_with_prov_bindings`, `fake_reasoning_run_consistency`.
- `backend/tests/test_agent_test_graph_context.py` — covers the new agent-test-context
  composition and its consumption inside `AgentTestService.run_agent_test`.
- `backend/tests/test_evidence_rest_surface.py` — covers the new evidence-artifacts REST
  routes over a temporary Postgres fixture.
- `backend/tests/test_mcp_tools_endpoint.py` — covers `GET /api/mcp/tools` enumeration and
  category bucketing.

**Updated files:**

- `backend/tests/test_semantic_read_model_stage3_execution.py` — add Stage 4 template names
  to the parametrized composer test.
- `backend/tests/test_semantic_stage3_e2e.py` — leave as-is (Stage 4 does not regress Stage 3
  contracts); only the new Stage 4 e2e is added.

**Removed files:** none.

### 9.2 Frontend

**New files:**

- `frontend/tests/stage4-tools.spec.ts` — Playwright e2e covering: entity search happy path,
  empty state, scope filter, agent-test graph context rendering, MCP tools enumeration, OWL
  consistency section in governance, evidence drawer open/close.

**Updated files:**

- `frontend/tests/stage3-publish.spec.ts` — adjust `mockCommon` if it intercepts
  `/api/mcp/tools` or `/api/semantic/graph-sets/*/read-models/entity-search` (it should not,
  but the catch-all may need an extra branch).
- `frontend/tests/stage2-graph-derived.spec.ts` — verify no regression on EntitiesPage after
  removing the unused `EntitySearchResult` type.

## 10. Migration Strategy

### 10.1 Release Sequence

1. Land Phase A (read models) — backend only, no UI consumer; safe to ship behind the
   existing `/api/semantic/graph-sets/{gsid}/read-models/{model_name}` route.
2. Land Phase B (REST additions) — `/api/mcp/tools` and `/api/projects/{pid}/evidence-artifacts`
   routes are net-new; no breaking change.
3. Land Phases C and D (frontend) — page additions only; no existing route breaks.
4. Land Phase E (cleanup) — remove dead `EntitySearchResult` type and CSS residue; no behavior
   change.

No data migration script is needed.

### 10.2 Data Preservation

- `evidence_artifacts` and `evidence_chunks` tables are read-only for Stage 4.
- `reasoning_runs` rows produced before Stage 4 are still readable through the new
  `owl-consistency-summary` composer.
- No RDF graph is mutated by Stage 4 read models.

## 11. Happy-Path E2E Plan

1. Open the workspace with a project + ontology + graph set already created (Stage 3 fixture).
2. Navigate to **Tools → Search**. Type "acme". Assert one row labeled "Acme Corp" with the
   `[asserted]` chip.
3. Apply the `Asserted` scope filter. Assert the row count is unchanged.
4. Switch the filter to `owl_inferred`. Assert the row count drops to 0 (no inferred rows
   seeded in this fixture).
5. Navigate to **Tools → Agent test**. Type "What is Acme Corp?" and run. Assert the answer
   panel populates and `graph_context.entries` contains the Acme Corp entry with the
   `[asserted]` chip.
6. Navigate to **Tools → MCP tools**. Assert the catalog shows ≥ 30 tools, including
   `compile_and_apply_canonical_command`.
7. Navigate to **Knowledge → Facts**. Open the fact drawer for the "Acme is a manufacturer"
   fact. Assert the drawer shows the bound chunk with `document_filename`,
   `sequence`, and `text_preview`.
8. Navigate to **Governance → Graph Governance**. Scroll to the new **OWL Consistency**
   section. Assert it shows `consistent: true`, `entailment_count: N`, and `is_stale: false`
   for the freshly seeded reasoning run.

## 12. Implementation Order and Subagent Decomposition

| Phase | Title | Subagent | Dependencies | Verify gate |
| --- | --- | --- | --- | --- |
| A | Backend read models | `stage4-backend-readmodels` | none | `uv run pytest backend/tests/test_semantic_stage4_e2e.py backend/tests/test_agent_test_graph_context.py` |
| B | Backend REST + agent-test refactor | `stage4-backend-rest` | A | `uv run pytest backend/tests/test_evidence_rest_surface.py backend/tests/test_mcp_tools_endpoint.py backend/tests/test_agent_test_graph_context.py` |
| C1 | Frontend `EntitiesSearchPage` | `stage4-frontend-search` | A | `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Search` |
| C2 | Frontend `AgentTestPage` rewrite | `stage4-frontend-agent` | A, B | `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Agent` |
| C3 | Frontend `McpToolsPage` rewrite | `stage4-frontend-mcp` | B | `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools MCP` |
| D1 | Frontend `EvidenceExplorer` panel | `stage4-frontend-evidence` | A, B | `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Evidence` |
| D2 | Frontend OWL consistency section | `stage4-frontend-consistency` | A | `cd frontend && pnpm tsc --noEmit && pnpm test stage4-tools Consistency` |
| E | Cleanup sweep + nav wiring | `stage4-frontend-cleanup` | C1, C2, C3, D1, D2 | `cd frontend && pnpm tsc --noEmit && pnpm test` |
| F | Playwright e2e | `stage4-e2e` | E | `cd frontend && pnpm test stage4-tools` |
| G | Status flip + spec mark | `stage4-cleanup` | F | `git log --oneline | grep "Stage 4"` |

C1, C2, C3, D1, D2 may run in parallel once Phase B lands.

### 12.1 Verification Gates

Each phase's verify gate is **mandatory** before handing off. Subagents must paste the actual
command output (not a summary) into the result message. The orchestrator inspects the output
and either approves or asks for review fixes inline.

## 13. Open Questions

These are not blocking. The implementation makes a defensible choice for each; they are
flagged here so a reviewer can challenge the choice.

- **`agent-test-context` keyword extraction.** Default is "split on whitespace, drop tokens
  ≤ 3 chars, lowercase". For CJK questions this is wrong — a Chinese question with no spaces
  will collapse to one giant token. *Decision:* ship the naive tokenizer; revisit when the
  Stage 4 e2e grows a CJK fixture.
- **Evidence chunk IRI convention.** The `prov:wasDerivedFrom` lookup assumes chunk IRIs use
  `tag:ontology-platform.internal,2026:evidence/{doc_id}/{sequence}`. *Decision:* this matches
  the Phase 2 namespace mapping spec; if it drifts, the composer fails open (returns empty
  `evidence_bindings`), which is the correct fallback for the drawer.
- **`/api/mcp/tools` category bucketing.** The MCP registry has no built-in category field.
  *Decision:* bucket by the `tools/{file}.py` source filename: `system`, `interview`,
  `semantic`. This is purely presentational.
- **`owl-consistency-summary` staleness.** The composer marks the run stale if *any* member
  graph has been edited since `finished_at`. A more precise signal would compare only against
  the ontology graph (since consistency is ontology-only). *Decision:* keep the broader signal
  for Stage 4 — over-flagging staleness is safer than under-flagging.
