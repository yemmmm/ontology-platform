# Semantic Stage 3 — Publish Rebuild Design

- **Date:** 2026-07-06
- **Scope driver:** `docs/semantic/functional-semantic-load-inventory.md` → Stage 3 — Publish
- **Architecture approach:** Graph-set native, read-model first, hard-cut legacy removal
- **Status:** Implemented

## 1. Goal and Non-Goals

### Goal

Finish the Publish stage semantic refactor and complete the legacy cutover that Stage 2
deferred. Three deliverables:

1. **`PublicationPage`** is rewritten as a graph-set readiness dashboard. "Publish"
   becomes "lock ontology/data graphs in this graph set + export a package". The
   draft→published state machine is retired (ADR 0004).
2. **`VersionsPage`** is rewritten as `GraphSetHistoryPage`. The `version` concept is
   removed entirely; a "version" is now a frozen graph set, and diff is the RDF delta
   between two graph sets.
3. **Legacy hard-removal.** All endpoints, services, models, migrations, and MCP tools
   that implement the draft→published state machine are deleted in a single hard-cut
   release. No shadow mode (Stage 2 was shadow; Stage 3 ends it).

### Non-Goals

- **Stage 4 — Tools.** `EntitiesSearchPage`, `AgentTestPage`, `EvidenceExplorer`,
  `McpToolsPage` rebuilds are out of scope.
- **Stage 1 — Topology canvas.** Still a placeholder.
- **New semantic MCP tools to replace the deleted legacy ones.** MCP rebuild is a
  follow-up, sized separately. Legacy tools are simply removed here; new ones land later.
- **OWL consistency dashboard.** Knowledge-conflicts are deleted with the rest; the new
  OWL consistency section of the governance dashboard is a Stage 4 deliverable.
- **Cross-ontology graph sets.** A graph set still belongs to exactly one ontology.

## 2. Locked-In Decisions

| Decision | Resolution | Source |
| --- | --- | --- |
| Migration window | **Hard cut** — legacy endpoints removed in the same release as the new UI | design dialogue 2026-07-06 |
| `version` concept | **Removed.** The new page is `GraphSetHistoryPage`; a "version" is a frozen graph set — i.e., a graph set whose every member has `editable=false` (status computed from members, no new column) | design dialogue 2026-07-06 |
| Publish semantics | Lock all editable graphs in the set + export a package. Two separate API calls; no transactional endpoint | ADR 0004 §Versioning |
| Diff semantics | RDF delta between two graph sets, computed by a new read-model template. Per-graph-role breakdown | ADR 0004 §Versioning |
| Legacy data | `fact_claims`, `rule_definitions`, `unanchored_knowledge`, `proposals`, `publication_gates` etc. tables are **dropped**. Stage 2 already migrated active data to RDF | design dialogue + grep verification |
| Editability reuse | The existing `PATCH /graphs/{iri}/editability` endpoint drives publish. No new canonical-write kind | ADR 0004 + Phase 4 |
| Read-model reuse | Publication readiness reuses the existing `graph-set-staleness` composer; only a thin wrapper template is added | Explore agent recommendation |

## 3. Shared Foundations

Stage 3 builds on the substrate that Stage 1/2 already delivered. Nothing here is new
infrastructure.

### 3.1 Graph Set Context

Every Stage 3 page operates inside a graph set, exactly as Stage 2 pages do. The active
graph set id is provided by `GraphSetSelector` and persisted in the URL param
`graphSet`. Same contract; no change.

### 3.2 Read-Model Contract

Stage 3 read-models reuse the existing endpoint and decorator:

```
GET /graph-sets/{graph_set_id}/read-models/{name}?field_set=&allow_stale_derived=
```

Templates live in `backend/app/services/semantic_sparql_templates.py`. Composer logic
lives in `backend/app/services/semantic_read_model.py`. Stage 3 adds two new templates
and one new composer (§4).

### 3.3 Editability API

`PATCH /api/semantic/graphs/{graph_iri:path}/editability` (already implemented at
`backend/app/api/semantic.py:393`) flips the `editable` flag on a single named graph.
Publish = call this for every editable graph in the set.

### 3.4 Graph-Set Export

`GET /api/semantic/graph-sets/{graph_set_id}/export` (already implemented at
`backend/app/api/semantic.py:1301`) returns the dataset package. No change.

## 4. Read-Model Contracts (New)

Three new templates land with Stage 3. All are added to the existing `_TEMPLATES` dict
in `backend/app/services/semantic_sparql_templates.py`.

### 4.1 `publication-readiness`

Aggregates per-graph-set readiness signals. Implemented as a composer (like
`graph-set-staleness`) because the row is a single object, not a list.

```python
ReadModelTemplate(
    name="publication-readiness",
    projection_version="1",
    required_roles=["asserted_ontology", "asserted_data"],
    needs_reasoning=True,
    needs_rules=True,
    default_limit=1,
    assertion_kind=None,           # composer-owned
    evidence_status=None,          # composer-owned
    primary_iri_variable="",       # composer
    body="# template: publication-readiness\n# delegated to _compose_publication_readiness\n",
)
```

Composer `_compose_publication_readiness` (in `semantic_read_model.py`) builds the
envelope:

| Field | Type | Source |
| --- | --- | --- |
| `graph_set_id` | string | request |
| `ready` | bool | AND of all gates |
| `gates` | `list[GateStatus]` | composed (see below) |
| `blockers` | `list[string]` | gates with `status="blocked"` |
| `warnings` | `list[string]` | gates with `status="warning"` |
| `editable_graph_count` | int | members with `editable=true` |
| `editable_graphs` | `list[{graph_iri, role}]` | members with `editable=true`; the publish modal iterates this list to lock each graph |
| `last_published_at` | string? | `graph_set_metadata.last_published_at` if any |

`GateStatus` shape:

```typescript
{
  gate: "validation_stale" | "reasoning_stale" | "rule_stale"
      | "missing_evidence" | "open_edits" | "projection_freshness"
      | "shape_drift";
  status: "passed" | "warning" | "blocked";
  details: { latest_run_id?: string; staleness_state?: string; count?: number };
}
```

Implementation reuses:
- `_compose_graph_set_staleness` (`semantic_read_model.py:322`) — already aggregates
  validation/reasoning/rule staleness per member.
- `_missing_evidence_count` (`semantic_read_model.py:387`) — already counts missing
  evidence per set.
- New helper `_open_edits_count(graph_set_id)` — counts `SemanticEditAuditModel` rows
  with `applied=false` or `status="pending"` for the set's graphs.
- New helper `_projection_freshness(graph_set_id)` — joins
  `SemanticProjectionManifestModel` `last_run_at` against `now()`.

`field_set` param: `summary` (default) returns `{ready, blockers, warnings}` only;
`detail` returns the full envelope including per-gate `details`.

### 4.2 `graph-set-history-list`

Lists graph sets in scope. Plain SPARQL/SQL hybrid (the list itself comes from
Postgres `SemanticGraphSetModel`, but staleness is enriched).

| Field | Type | Source |
| --- | --- | --- |
| `graph_sets` | `list[GraphSetHistoryEntry]` | composed |
| `total` | int | total in scope |

`GraphSetHistoryEntry` shape:

```typescript
{
  graph_set_id: string;
  status: "editable" | "locked" | "superseded";
  created_at: string;
  locked_at: string | null;
  source_signature: string;
  member_count: int;
  latest_derived_pointer_at: string | null;
  ready: boolean | null;        // null if never computed
}
```

Implementation: Postgres query on `SemanticGraphSetModel` filtered by `scope_type`
(`ontology` / `project`) and `scope_id`, joined with
`SemanticGraphSetMemberModel.editable` to compute `status`, and
`SemanticDerivedResultPointerModel.became_current_at` for
`latest_derived_pointer_at`. The `ready` flag calls `_compose_publication_readiness` for
the most recent set and skips for historical ones (configurable via `?include_ready=`).

### 4.3 `graph-set-delta`

Computes the RDF delta between two graph sets. Inputs:

- `base_graph_set_id` (path param)
- `target_graph_set_id` (query param `?target=`)

Output: per-role delta.

| Field | Type |
| --- | --- |
| `base_graph_set_id` | string |
| `target_graph_set_id` | string |
| `roles` | `list[RoleDelta]` |

`RoleDelta` shape:

```typescript
{
  role: "asserted_ontology" | "asserted_data" | "shape_graph_generated" | ...;
  base_graph_iri: string;
  target_graph_iri: string;
  added: list[{ subject, predicate, object }];     // capped at limit
  removed: list[{ subject, predicate, object }];
  counts: { added: int; removed: int; };
}
```

Implementation: For each role present in both sets, run a SPARQL `CONSTRUCT` query
against `base_graph_iri`, another against `target_graph_iri`, diff the triple sets in
Python. Cap each side at `limit` (default 200) triples; full counts come from a separate
`SELECT COUNT` query. When a role exists only on one side, the missing side is treated
as an empty graph.

The existing `RdfStoreRepository.apply-dataset-delta` (Phase 7) is the inverse operation
— it applies a delta. Stage 3 reads diffs but does not write them.

## 5. Canonical Writes

**No new canonical-write kinds are added.** Publish is a two-step client-driven flow:

1. For each editable graph in the set: `PATCH /api/semantic/graphs/{iri}/editability`
   with `{editable: false}`.
2. `GET /api/semantic/graph-sets/{id}/export` to materialize the package.

The frontend wraps these two steps in a single confirmation modal (§7.1). If step 1
partially fails (some graphs lock, some don't), the user is told which graphs failed and
given the option to retry or rollback. Rollback is per-graph unlock — no transactional
compensation.

## 6. Backend Hard-Cut Removals

### 6.1 Endpoints Deleted

`backend/app/api/governance.py` (entire router, registered at `routes.py:27`) is removed.
This drops:

| Method | Path | Handler line |
| --- | --- | --- |
| POST | `/ontologies/{id}/versions` | `governance.py:36` |
| GET | `/ontologies/{id}/versions` | `governance.py:45` |
| GET | `/versions/{from}/diff/{to}` | `governance.py:56` |
| POST | `/proposals` | `governance.py:66` |
| GET | `/proposals/{id}` | `governance.py:76` |
| GET | `/ontologies/{id}/proposals` | `governance.py:81` |
| POST | `/proposals/{id}/validate` | `governance.py:92` |
| POST | `/proposals/{id}/apply` | `governance.py:102` |
| PATCH | `/versions/{id}/mutability` | `governance.py:113` |
| POST | `/versions/{id}/publish` | `governance.py:123` |
| GET | `/versions/{id}/publication-readiness` | `governance.py:136` |
| GET | `/ontologies/{id}/knowledge-conflicts` | `governance.py:144` |
| POST | `/knowledge-conflicts/{id}/resolve` | `governance.py:149` |

The `Sunset` header (set to `Sat, 1 Nov 2026`) is no longer relevant — these die on
Stage 3 release.

### 6.2 Services Deleted

- `backend/app/services/publication.py` — entire file (`evaluate_readiness`,
  `publish_version`, all gate evaluators, `GATE_ORDER`, `CORE_ASSERTION_LAYERS`).
- `backend/app/services/governance.py` — entire file (`create_draft_version`,
  `list_versions`, `version_diff`, `set_version_mutability`, `publish_version`,
  `create_proposal`, `validate_proposal`, `apply_proposal`, `proposal_detail`,
  `list_proposals`, `list_conflicts`, `resolve_conflict`, `_schema_snapshot`).
- All callers updated. The Stage 2 e2e tests and Stage 2 read-models already bypass
  these services.

### 6.3 Schemas Deleted

In `backend/app/api/schemas.py`: `OntologyVersionCreate` (`:659`),
`OntologyVersionRead` (`:663`), `VersionMutabilityUpdate` (`:679`), `ProposalCreate`
(`:782`), `ProposalRead` (`:799`), `VersionDiffRead` (`:828`),
`PublicationReadinessRead` (`:1099`), `PublicationConfirm` (`:1107`),
`KnowledgeConflictRead`, `ConflictResolutionCreate`.

### 6.4 Models Deleted

In `backend/app/repositories/models.py`:

- `VersionStatus` enum (`:28`)
- `OntologyVersionModel` (`:114`) and the `ontology_versions` table
- `ProposalModel` (`:457`) and `proposals`
- `ReviewBatchModel` (`:491`) and `review_batches`
- `EvidenceModel` (`:514`) and `evidence` (legacy evidence rows; Stage 2 evidence lives
  in `graph/evidence/{project_id}`)
- `ReviewDecisionModel` (`:534`) and `review_decisions`
- `ValidationRunModel` (`:550`) — legacy Postgres validation runs; semantic runs live in
  `SemanticValidationRunModel`
- `PublicationGateModel` (`:566`) and `publication_gates`
- `FactClaimModel` (`:582`) — legacy Postgres facts; Stage 2 reads facts from RDF
- `RuleDefinitionModel` (`:626`) — legacy Postgres rules; semantic rules live in
  `SemanticRuleDefinitionModel`
- `UnanchoredKnowledgeModel` (`:656`)
- `KnowledgeConflictModel` — conflict rows; conflicts fold into the OWL consistency
  report in Stage 4

The `ontologies` table itself stays, but its `current_version_id` field (`models.py:768`)
is removed. The `OntologyModel.status` enum drops the values that imply the
draft→published lifecycle if those values are now unused (verify at deletion time).

### 6.5 Migrations

One new Alembic migration: `backend/migrations/versions/0017_drop_legacy_governance.py`.
Single-transaction drop of all tables in §6.4, in dependency order (children first):

```
review_decisions
evidence
review_batches
validation_runs          (legacy table)
publication_gates
fact_claims              (legacy table)
rule_definitions         (legacy table)
unanchored_knowledge
knowledge_conflicts
proposals
ontology_versions
```

Then `ALTER TABLE ontologies DROP COLUMN current_version_id`.

`downgrade()` is a no-op that raises `NotImplementedError` — once dropped, legacy data
cannot be reconstructed. The migration is one-way.

### 6.6 MCP Tools Deleted

- `backend/app/mcp/tools/proposals.py` (10 tools) — entire file
- `backend/app/mcp/tools/publication.py` (1 tool) — entire file
- Registration calls in `backend/app/mcp/tools/__init__.py:17,18,28,32` removed.

No new MCP tools replace them in Stage 3 (Non-Goal §1).

### 6.7 Tests Deleted

- `backend/tests/test_publication_service.py` — entire file
- `backend/tests/test_governance_service.py` — version/proposal/mutability/diff cases
  (proposal-specific only; keep conflict-resolution cases if they survive — they don't,
  conflicts are deleted)
- `backend/tests/test_mcp_surface.py` — `get_publication_readiness` (`:59`),
  `publish_version` (`:92`) entries
- `backend/tests/test_mcp_payloads.py` — proposal / publication payload cases
- `backend/tests/test_v04_acceptance.py`, `test_v05_acceptance.py` — version lifecycle
  scenarios rewritten or dropped depending on what they assert

### 6.8 Frontend Files Deleted

- `frontend/src/pages/PublicationPage.tsx` — replaced by new file (§7.1)
- `frontend/src/pages/VersionsPage.tsx` — replaced by `GraphSetHistoryPage.tsx` (§7.2)
- `frontend/src/pages/governanceTypes.ts` — `OntologyVersion`, `GovernancePageContext`
  types deleted (any types still used by Stage 2 governance pages are migrated into the
  Stage 5 governance module's local types)

## 7. Frontend Rebuilds

### 7.1 `PublicationPage` (readiness dashboard)

**File:** `frontend/src/pages/PublicationPage.tsx` (rewritten in place).

**Layout:**

```
┌─ Publication Readiness ─────────────────────────────┐
│ Graph set: <selector>          [Refresh]            │
├─────────────────────────────────────────────────────┤
│ Status: ● Ready / ◐ Has warnings / ○ Blocked        │
│ Editable graphs: 4 / 6                              │
├─ Gates ─────────────────────────────────────────────┤
│  ✓ Validation      latest run #v-017, 2 min ago     │
│  ✓ Reasoning       latest run #r-009, 1 hour ago    │
│  ⚠ Rules           rule_run #rr-003, 3 days ago     │
│  ✓ Missing evidence  0 facts                        │
│  ⚠ Open edits      2 pending semantic edits         │
│  ✓ Projection      Neo4j fresh, Topology fresh      │
│  ✓ Shape drift     shapes match OWL                 │
├─ Per-graph state ───────────────────────────────────┤
│  graph/ontology/acme     editable                   │
│  graph/data/acme         editable                   │
│  graph/shapes/acme       locked (generated)         │
├─────────────────────────────────────────────────────┤
│           [Lock all graphs and export package]      │
└─────────────────────────────────────────────────────┘
```

**Hooks:**

- `useGraphSetReadiness(graphSetId)` — calls `readModel(graphSetId,
  "publication-readiness", {field_set: "detail"})`, polls every 30s while tab visible.
  Reuses the `readModel<T>()` helper from `frontend/src/semanticApi.ts:370`.

**Publish action:**

The "Lock all graphs and export package" button opens a confirmation modal listing the
exact graphs that will be locked. On confirm:

1. For each `editable_graph` in `gates.editable_graphs`:
   `updateGraphEditability(graph_iri, {editable: false})`.
2. On success: `window.location = buildGraphSetExportUrl(graphSetId)` to trigger the
   download.
3. On partial failure: stop, show which graphs failed, offer "Retry failed" or
   "Unlock all" (which calls `updateGraphEditability` with `{editable: true}` on the
   graphs that did lock).

No optimistic updates — every gate toggle refetches readiness.

### 7.2 `GraphSetHistoryPage`

**File:** `frontend/src/pages/GraphSetHistoryPage.tsx` (replaces `VersionsPage.tsx`).

**Layout:**

```
┌─ Graph Set History ─────────────────────────────────┐
│ Ontology: <selector>           [Create new graph set]│
├─ List ─────────┬─ Detail / Delta ────────────────────┤
│ ▸ gs-019  ●  │ Selected: gs-019                     │
│   gs-018  🔒 │ Status: editable   Created: 2h ago   │
│   gs-017  🔒 │ Members: 6 (3 editable, 3 locked)    │
│   gs-016  🔒 │ Effective pointers:                  │
│               │   validation:  vp-017 (2 min ago)    │
│ ── Diff ──── │   reasoning:   rp-009 (1h ago)       │
│ Base: gs-019 │   rules:       rp-003 (3d ago) ⚠     │
│ Target: gs-017                                    ▼ │
│ [Compute delta]                                     │
│                                                     │
│ (when delta computed:)                              │
│ ▸ asserted_ontology  +12 / -3                       │
│ ▸ asserted_data      +147 / -22                     │
│ ▸ shape_graph_generated  (unchanged)                │
└─────────────────────────────────────────────────────┘
```

**Hooks:**

- `useGraphSetHistory(scopeType, scopeId)` — calls
  `readModel(graphSetId_for_scope, "graph-set-history-list")`. Reuses the scope
  resolution: if `scopeType === "ontology"`, the read-model service filters by that
  ontology id.
- `useGraphSetDelta(baseId, targetId)` — lazy; only fires when the user clicks
  "Compute delta". Calls `readModel(baseId, "graph-set-delta", {target: targetId})`.

**No create flow in Stage 3.** The "Create new graph set" button links to the existing
`/api/semantic/graph-sets` POST endpoint wrapped by `GraphSetSelector`. No new UI is
built for it.

### 7.3 Routing and Navigation

In `frontend/src/App.tsx`:

- Tab id `"versions"` → renamed `"graph-set-history"`. Stage identifier in
  `workflowStageMap` (`:196`) keeps `publish: "graph-set-history"`.
- Tab id `"publication"` stays (the readiness dashboard is still the publish action).
- The lock-guard regex `/^\/versions\/[^/]+\/mutability$/` (`App.tsx:1030-1032`) is
  removed entirely — no mutability concept remains.
- `version` URL param that drove `VersionsPage` is replaced by `graphSet` everywhere
  (already the Stage 2 convention).
- `BuildOverviewPage` callbacks (`App.tsx:1040`, `PublicationPage.tsx:151`) updated to
  drop `versions` references.
- Lazy Stage2 FactAuditPage swap (`App.tsx:1051-1067`) simplified — no more conditional
  PublicationPage fallback.

### 7.4 i18n

In `frontend/src/i18n/zh.ts` and `translations.ts`:

- New keys under `publication.readiness.*`, `graphSetHistory.*`, `delta.*`.
- Removed keys under `versions.*`, `publication.gate.*` (legacy gate taxonomy),
  `mutability.*`, `proposals.*`.

## 8. Error Handling

| Scenario | UX |
| --- | --- |
| Readiness read fails | Show "Readiness unavailable" with retry; do not render gates from stale cache |
| `graph-set-delta` over very large sets (>10k triple diff) | Cap at `limit` per role; show `+N more` and a "Download full delta" link that calls the same endpoint with `?limit=10000` |
| Publish: one graph fails to lock | Stop the loop; show partial state; offer retry or rollback |
| Publish: export fails after all graphs locked | Graphs stay locked (intentional — locking succeeded); show "Export failed, retry download" with a direct link to `/graph-sets/{id}/export` |
| Read-model returns `allow_stale_derived=false` and a derived graph is stale | Return HTTP 409 with `{error: "derived_stale", graph_iri, latest_run_id}`; UI shows "Run reconciliation first" |

## 9. Testing Strategy

### 9.1 Backend

**New files:**

- `backend/tests/test_semantic_stage3_e2e.py` — happy-path step-by-step coverage.
  Mirrors `test_semantic_stage2_e2e.py` structure (§11).
- `backend/tests/test_semantic_read_model_stage3_execution.py` — execution-level tests
  for the three new templates, including `FakeStore` for delta computation.

**Updated files:**

- `backend/tests/test_mcp_surface.py` — remove `get_publication_readiness` and
  `publish_version` from the expected registry.
- `backend/tests/test_semantic_phase6_api.py` — add cases for the new templates'
  routing through `/graph-sets/{id}/read-models/{name}`.

**Deleted files:**

- `backend/tests/test_publication_service.py`
- `backend/tests/test_governance_service.py` (entire file — its only purpose was the
  deleted module)
- Cases inside `test_v04_acceptance.py` and `test_v05_acceptance.py` that walk the
  draft→published lifecycle are rewritten or removed.

### 9.2 Frontend

**New file:**

- `frontend/tests/stage3-publish.spec.ts` — Playwright spec covering:
  - Readiness dashboard renders all 7 gates from a mocked read-model response
  - "Lock all + export" sequence fires `updateGraphEditability` for each editable graph
    then triggers export
  - Partial failure shows the rollback affordance
  - `GraphSetHistoryPage` lists graph sets in scope
  - Diff computation renders per-role breakdown

**Updated files:**

- `frontend/tests/workbench-smoke.spec.ts` — replace mocked `/ontologies/{id}/versions`
  and `/versions/{id}/*` calls with the new read-model mocks.
- `frontend/tests/semantic-governance.spec.ts`, `stage2-graph-derived.spec.ts`,
  `language-switch.spec.ts` — same replacement.

## 10. Migration Strategy

### 10.1 Release Sequence

Stage 3 ships as a single release. Order within the release:

1. Land backend read-model additions (§4) and tests.
2. Land backend hard-cut removals (§6) and migration `0017_*.py`.
3. Land frontend rebuilds (§7) and Playwright spec (§9.2).
4. Land i18n and cleanup.

The release commits land on `main` together. There is no point in the release window
where the new UI calls legacy endpoints or the old UI calls new endpoints — both halves
are atomic.

### 10.2 Data Preservation

Stage 2 already migrated active semantic data to RDF. The legacy tables being dropped
contain either:

- **Duplicate data** (already in RDF) — drop without backup.
- **Legacy-only data** (e.g., abandoned `proposal` rows from v0.4 acceptance tests) —
  drop without backup.

If a deployment has production legacy data that needs preserving, the operator can run
`GET /api/semantic/graph-sets/{id}/export` on each active graph set **before** the
migration. This is documented in the migration's `docstring` but not automated.

## 11. Happy-Path E2E Plan

`backend/tests/test_semantic_stage3_e2e.py` follows the §11 pattern from Stage 2. Each
step is its own test function; tests share a session-scoped fixture that builds the
graph set once.

1. **Build the graph set.** Create an ontology, register the named graphs, build the
   set with `asserted_ontology` + `asserted_data` + `shape_graph_generated` members.
2. **Seed the ontology graph.** Run a `create_class` canonical-write; verify the class
   lands in `graph/ontology/{id}`.
3. **Seed the data graph.** Run a `create_entity` canonical-write; verify it lands in
   `graph/data/{id}`.
4. **Trigger validation + reasoning.** POST `/graph-sets/{id}/validation-runs` and
   `/reasoning-runs`; wait for completion.
5. **Read readiness — warning case.** Assert `ready=true`, `warnings` includes
   "open_edits" (because we just wrote without locking; pending edits are
   recoverable so they warn rather than block). Use `field_set=detail`.
6. **Lock the ontology graph.** `PATCH /graphs/{iri}/editability {false}`. Read
   readiness again — `editable_graph_count` decreased.
7. **Lock the data graph.** Same. Read readiness — `ready=true`.
8. **Export.** `GET /graph-sets/{id}/export`; assert the package contains the locked
   ontology + data graphs.
9. **Build a second graph set.** Same shape but seed with one fewer entity. Readiness
   dashboard on the new set shows `ready=false`.
10. **Compute delta.** `GET /graph-sets/{gs1}/read-models/graph-set-delta?target={gs2}`;
    assert `asserted_data.counts.removed >= 1` for the entity that was omitted.
11. **History list.** `GET /graph-sets/{gs1}/read-models/graph-set-history-list`;
    assert both sets appear with correct `status`.

## 12. Implementation Order and Subagent Decomposition

Stage 3 is executed by subagents to keep the main context lean. Dependencies are strict;
each phase gates the next.

| Phase | Subagent | Scope | Depends on |
| --- | --- | --- | --- |
| A | `stage3-backend-readmodels` | Add 3 templates + 2 composers + execution tests + stage3 e2e steps 1–7 (without removals) | — |
| B | `stage3-backend-removal` | Delete governance.py router + 2 services + 11 schemas + 12 models; add migration 0017; update MCP surface test; delete `test_publication_service.py` + `test_governance_service.py` | A passing |
| C | `stage3-frontend-publication` | Rewrite `PublicationPage.tsx`; new hook `useGraphSetReadiness`; delete legacy `governanceTypes.ts` exports | A + B passing |
| D | `stage3-frontend-history` | New `GraphSetHistoryPage.tsx`; new hooks `useGraphSetHistory`, `useGraphSetDelta`; delete `VersionsPage.tsx` | A + B passing |
| E | `stage3-frontend-wiring` | Update `App.tsx` routing, tab ids, lock guard, i18n keys; remove references from `BuildOverviewPage` callbacks | C + D passing |
| F | `stage3-tests-e2e` | Add `frontend/tests/stage3-publish.spec.ts`; update existing specs that mock legacy endpoints | E passing |
| G | `stage3-cleanup` | Final grep sweep for stragglers (`ontology_versions`, `OntologyVersion`, `proposals/`, `publication-readiness`); run full test suite | F passing |

Phases C and D run in parallel. All others are sequential.

### 12.1 Verification Gates

Before each phase hands off:

- `uv run pytest backend/tests/ -x` must pass.
- `uv run pytest backend/tests/test_semantic_stage3_e2e.py -x` must pass.
- For frontend phases: `cd frontend && npm run typecheck && npm run test` must pass.
- For phase F: `cd frontend && npx playwright test stage3-publish.spec.ts` must pass.

The plan (§writing-plans output) encodes these gates as explicit checkboxes.

## 13. Open Questions

These do not block the design but should be answered during implementation:

- **`ontologies.status` enum.** Does it still use `DRAFT` / `PUBLISHED` / `DEPRECATED`
  values after the lifecycle is removed? If unused, drop them; if used by external
  callers, leave them alone.
- **`BuildOverviewPage` version status.** Stage 1 disposition **P** noted that
  `BuildOverviewPage` reads version/proposal status. Stage 3 removes those endpoints.
  Either `BuildOverviewPage` was already updated in Stage 1, or it needs a small patch
  in Phase E. Verify at start of Phase E.
- **`SemanticGraphSetModel.status` semantics.** "Locked" vs "superseded" is implicit
  (derived from members + pointer state). Phase A must decide whether to add an explicit
  `status` column or compute it on read. Recommendation: compute on read; the existing
  `graph_set_metadata` JSONB can hold `locked_at` for the rare explicit case.
