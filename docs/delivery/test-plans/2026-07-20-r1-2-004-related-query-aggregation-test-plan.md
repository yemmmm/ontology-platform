# R1.2-004 相关查询表达式联合语义上下文聚合共享测试计划

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-004
- Design:
  `docs/delivery/designs/2026-07-20-r1-2-004-related-query-aggregation-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-20-r1-2-004-related-query-aggregation-delivery-record.md`
- Plan status: reviewed PASS; product implementation and execution pending

## 1. Purpose and completion boundary

This is the single shared test plan for the future R1.2-004 implementation. It covers the REST,
MCP, shared-service, retrieval, context, pagination, authorization, degradation, documentation, and
real-runtime contracts frozen by the design.

The current delivery is documentation only. Passing Markdown checks and plan review validates the
design artifacts, not the product requirement. R1.2-004 can be marked `已实现` only after the future
implementation passes all mandatory gates in section 9 and an independent tester appends a PASS
round to section 11.

## 2. Test levels and evidence

- Service unit/integration tests prove normalization, fusion, ordering, root attribution,
  pagination, cursor binding, and degradation with controlled fixtures.
- REST tests prove validation, compatibility fields, errors, and authenticated scope behavior.
- MCP tests prove schema parity and core-result parity with REST.
- PostgreSQL + pgvector + Oxigraph integration proves real scope/version/retrieval behavior. Mocks
  alone cannot prove these contracts.
- Runtime smoke tests prove the restarted application advertises and serves the reviewed contract.
- Documentation checks prove requirement, API/MCP docs, capability discovery, and status agree.

For parity assertions, volatile timestamps and transport-only metadata may be excluded; match
identity/order, evidence, completeness, page state, versions, and errors must agree.

## 3. Fixtures

### 3.1 Required semantic fixtures

1. A Dify reference Ontology containing the three independent topics used by acceptance:
   customer-support ticket, invoice reconciliation, and contract-risk review. It includes the
   current ordinary RDF resources and predicates for inputs, nodes, outputs, and explicit order.
2. A non-workflow Ontology, such as a product/catalog or people/organization graph, with related
   labels, aliases, mappings, literal facts, incoming/outgoing relations, and a shared neighbor.
3. Two authorized Ontologies containing the same resource IRI so cross-Ontology non-merging can be
   proved.
4. An unauthorized Project/Ontology containing tempting exact and semantic matches.
5. A current R1.2-003 vector projection fixture and a separate missing/stale/provider-failure
   fixture for degraded behavior.
6. A version-mutating fixture that can advance an Ontology `workspace_version` between cursor
   pages.

### 3.2 Controlled ranking fixture

The ranking fixture must include:

- one resource with one exact label/alias/Mapping/ID hit;
- one resource with several weak semantic hits;
- resources in the same evidence tier with different best scores;
- resources with the same tier and score but different distinct-expression support counts;
- a final tie resolved by the existing stable R1.2-003 keys;
- normalized duplicate expressions and reordered expression lists.

### 3.3 Cleanup ownership

All created records use a run-specific prefix and known Project/Ontology IDs. The test runner
records those IDs before mutation and deletes only those exact resources. If ownership cannot be
proved, cleanup is skipped and reported rather than deleting broad data.

## 4. Functional cases

### 4.1 Request and compatibility

| ID | Scenario | Expected result |
| --- | --- | --- |
| FQ-01 | `queries` has three related expressions | one fused response, original order echoed |
| FQ-02 | item is a full question rather than a short keyword | same retrieval path; no mode field |
| FQ-03 | valid but unrelated expressions are mixed | request is processed without relatedness warning/rewrite |
| FQ-04 | 1 and 8 expressions | accepted |
| FQ-05 | 0 or 9 expressions | stable validation error |
| FQ-06 | empty/blank item or item over 2000 characters | stable validation error |
| FQ-07 | aggregate trimmed input over 8000 characters | stable validation error |
| FQ-08 | `context_limit` is 0, 100, and 1000 | accepted with correct budget behavior |
| FQ-09 | `context_limit` below 0 or above 1000 | stable validation error |
| BC-01 | legacy REST request contains only `query` | accepted as a one-item list |
| BC-02 | legacy MCP call contains only `query` | accepted with REST-equivalent result |
| BC-03 | both `query` and `queries` are provided | stable validation error |
| BC-04 | neither field is provided | stable validation error |
| BC-05 | legacy response consumer reads `query.text` and `normalized_terms` | fields and meanings remain compatible |

### 4.2 Response and fusion

| ID | Scenario | Expected result |
| --- | --- | --- |
| RS-01 | several expressions match overlapping resources | one deduplicated `primary_matches` list only |
| RS-02 | no match under complete recall | `no_match`, complete recall, empty list |
| RS-03 | only related context would match status check | match status still depends only on primary list |
| RS-04 | one section truncates | section state differs correctly; top-level `truncated` is OR |
| FU-01 | one exact match versus several weak semantic hits | exact resource ranks first |
| FU-02 | same tier, different best score | best score ranks first |
| FU-03 | same tier and score, different distinct-expression support | greater support ranks first |
| FU-04 | all preceding keys tie | existing R1.2-003 tie-breaker is stable |
| FU-05 | reorder identical expression multiset | identities, scores, support, and ranking do not change |
| FU-06 | repeat normalized duplicate expressions | no support or score boost; originals still echoed |
| FU-07 | same IRI occurs in two Ontologies | two matches remain, keyed by Ontology and ID |
| FU-08 | ambiguous same-name resources | all remain with distinct evidence; no equivalence assertion |
| FU-09 | item matched by multiple expressions | expression indexes and evidence are preserved per item |

### 4.3 Context expansion

| ID | Scenario | Expected result |
| --- | --- | --- |
| CX-01 | depth 0 | matches only, empty context, no context cursor |
| CX-02 | default depth omitted | depth 1 behavior |
| CX-03 | depth 1 | direct literals, in/out relations, adjacent resources only |
| CX-04 | depth 2 and 3 | only requested additional graph distance is traversed |
| CX-05 | multiple matches retained on page | every match is expanded, not only rank one |
| CX-06 | shared item is one edge from root A and two edges from root B | emitted once with two exact `root_paths` distances |
| CX-07 | `context_limit=0` with depth 1 | matches unaffected; context empty by explicit budget |
| CX-08 | missing required/type/order fact in reference Ontology | no invented fact or business-specific missing field |
| CX-09 | nonlinear workflow topology | raw edges remain; platform does not create total order |

## 5. Pagination, scope, and security cases

### 5.1 Independent pagination

| ID | Scenario | Expected result |
| --- | --- | --- |
| PG-01 | matches exceed `limit`, context fits | only match page truncates; match cursor exists |
| PG-02 | matches fit, context exceeds `context_limit` | only context page truncates; context cursor exists |
| PG-03 | both exceed limits | both independent cursors exist |
| PG-04 | continue a match cursor | next global matches and their context start page return |
| PG-05 | continue a context cursor | only current match-page context continues |
| PG-06 | skip remaining context and use match cursor | next matches remain deterministic |
| PG-07 | paginate to exhaustion | no duplicates/omissions within the bound version |
| PG-08 | use match cursor as context cursor or reverse | `invalid_context_cursor` |
| PG-09 | tamper with cursor | `invalid_context_cursor`; no partial data |
| PG-10 | raw query text inspection | cursor does not contain raw expressions |
| PG-11 | submit both cursor inputs in one request | stable validation error; neither stream advances |
| PG-12 | vary SPARQL row and producer-phase encounter order | context page identities and total order remain identical |
| PG-13 | encounter a shared item from its roots in opposite order | item page position and sorted `root_paths` remain identical |

### 5.2 Cursor binding and authorization

| ID | Scenario | Expected result |
| --- | --- | --- |
| SC-01 | change queries, filter, mode, depth, or relevant page size | `context_cursor_mismatch` |
| SC-02 | two valid principals can see the same Project; principal B uses A's cursor | failure closed; project equality cannot authorize cursor reuse |
| SC-03 | access unauthorized Project/Ontology initially | existing R-008 error; no candidates |
| SC-04 | authorization is revoked between pages | continuation fails closed |
| SC-05 | workspace version/signature changes between pages | `context_snapshot_changed`; fresh query required |
| SC-06 | authorized multi-Ontology Project scope | only actual resolved/current Ontologies contribute |
| SC-07 | unauthorized Ontology has strongest exact match | it is absent from items, counts, warnings, and scores |
| SC-08 | cursor signer rotates/restarts with ephemeral key | stable invalid-cursor response, never mixed-version data |

## 6. Degradation and failure cases

| ID | Scenario | Expected result |
| --- | --- | --- |
| DG-01 | all expressions have current lexical/vector paths | overall completeness `complete` |
| DG-02 | one expression's vector path unavailable | available results preserved; overall `degraded` |
| DG-03 | several Ontologies/expressions degrade differently | warnings identify authorized scope and expression indexes |
| DG-04 | degraded response still has lexical match | `matched` plus degraded completeness |
| DG-05 | degraded response has no matches | `no_match` plus degraded completeness; not proof of absence |
| DG-06 | embedding response count/dimension invalid | affected vector path degrades; no corrupt fusion |
| DG-07 | overall request deadline reached during retrieval | deterministic degraded/error behavior per available evidence |
| DG-08 | invalid auth/scope/parameters/cursor | request fails; never converted into degradation |

## 7. Domain-boundary and documentation cases

| ID | Scenario | Expected result |
| --- | --- | --- |
| BD-01 | Dify customer-support fixture | generic facts let the Agent interpret workflow structure |
| BD-02 | invoice and contract topics queried separately | each uses the same generic contract; no workflow endpoint |
| BD-03 | non-workflow Ontology uses related expressions | identical response/status contract |
| BD-04 | search product code and public schemas | no Dify fixture names, `workflow-detail`, or business branches |
| BD-05 | API/MCP docs and capability discovery | canonical `queries`, compatibility alias, limits, cursors documented |
| BD-06 | requirement/status/design synchronization | R1.2-004 marked implemented only after independent PASS |

## 8. Performance and operational cases

| ID | Scenario | Expected result |
| --- | --- | --- |
| PF-01 | eight distinct hybrid expressions | one scope resolution and one bounded embedding batch normally used |
| PF-02 | provider advertises lower batch limit | bounded split preserves results and completeness semantics |
| PF-03 | three related expressions versus three naive complete calls | shared pipeline avoids repeated decoration/neighborhood work |
| PF-04 | max matches, context, and depth | request respects caps/deadline without memory or response explosion |
| PF-05 | concurrent workspace mutation | no mixed-version page; cursor continuation requests fresh query |

The implementation review must include instrumentation or controlled spies proving the number of
scope resolutions, embedding batches, and neighborhood expansions. Timing alone is insufficient.
It must also prove that REST injects the server-derived principal and that MCP forwards the
refreshed `_authorize_tool` principal into the shared service/cursor codec rather than using a
client-provided identity.
The real-runtime round also records p50/p95 for representative one- and eight-expression requests;
no fixed latency acceptance threshold is introduced until a repeatable environment baseline exists.

## 9. Future implementation completion gate

All of the following are mandatory before R1.2-004 is complete:

1. Focused backend tests for sections 4 through 8 pass.
2. Full backend suite passes with `cd backend && uv run pytest`.
3. REST and MCP parity is demonstrated against PostgreSQL + pgvector + Oxigraph.
4. Both a current-vector complete path and a missing/stale/provider-failure degraded path pass.
5. Dify and non-workflow fixtures prove the platform/reference-Ontology boundary.
6. API, MCP, capability-discovery, requirement, design, and operational docs are synchronized.
7. The local service is restarted and verified with repository-required status and health checks.
8. GitNexus impact analysis precedes symbol edits and `detect_changes()` confirms expected scope
   before commit.
9. An independent `requirement_tester` reviews the stable implementation and appends a PASS round.
10. Owned fixture cleanup is completed or an exact blocker is recorded.

Expected verification commands include:

```bash
cd backend && uv run pytest
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

Frontend build/Playwright checks are required only if the future implementation changes frontend
code or a visible UI/capability surface.

## 10. Current documentation-only verification

This delivery runs only:

- requirement/design/test-plan consistency review;
- link/path and Markdown hygiene checks;
- independent plan review for evidence-backed Critical/High design issues;
- Git diff/status and GitNexus change-scope review before the documentation commit.

No backend test result, runtime restart, or product behavior claim will be recorded for this phase.

## 11. Independent test rounds

No product test round has run because implementation is explicitly deferred. Future independent
testers append rounds here without removing earlier failures.

| Round | Stable state | Result | Defects or unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| Pending | no implementation handoff | NOT RUN | all product cases deferred by approved scope | this plan |
| Independent Round 1 (2026-07-20, requirement_tester) | branch `agent-semantic-layer-platform`, base commit `326c966d2f994610e186f1017caec8f46ff307b9`, dirty worktree (developer's uncommitted R1.2-004 implementation plus this tester's new `backend/tests/test_semantic_context_query_independent.py`); live `ontology-platform.service` running the **base commit only** (capability surface NOT yet deployed). | PASS-with-DEFERRED — no Critical/High defects found in the unit-testable contract surface; design-contract review agrees with §4–§7. Live-stack/runtime/cleanup gates deferred per design §9. | DEFERRED (require live PostgreSQL + pgvector + Oxigraph or a restarted service running the new code): FQ-02/03 (question vs keyword; unrelated expressions against real Dify fixture), FQ-08 (context_limit 0/100/1000 budget behavior with real neighborhood), RS-02/04 (real-data no-match and truncation), FU-07/08 (cross-Ontology same IRI; ambiguous names on real fixture), CX-01/02/03/04/05/06/08/09 (real graph traversal, depth 0/1/2/3, multi-root shared item, Dify boundary, nonlinear topology), PG-02/03/05/06/07/11/12/13 (real-data context truncation, both-cursor input, encounter-order invariance), SC-03/04/06/07 (R-008 fail closed against live authorization; revoked authorization; multi-Ontology scope; unauthorized strongest match), DG-01/03/05/06/07 (complete vs degraded mix on real provider; deadline; invalid provider payload), BD-01/02/03/04/06 (Dify fixtures, requirement status sync, runtime restart verification, owned cleanup), PF-02/03/04/05 (provider batch split; naive-call comparison; max budget; concurrent mutation). Section 9 items 3–7 and 10 also remain deferred (PostgreSQL+pgvector+Oxigraph parity; runtime restart; documentation/status sync after independent PASS; cleanup). | see "Independent Round 1 — evidence" below |

### Independent Round 1 — scope and method

- Stable state: branch `agent-semantic-layer-platform`, base commit `326c966d2f994610e186f1017caec8f46ff307b9`; dirty worktree with 19 changed files (15 modified, 4 new including this tester's `backend/tests/test_semantic_context_query_independent.py`).
- Method: read the frozen design (`docs/delivery/designs/2026-07-20-r1-2-004-related-query-aggregation-design.md` §4–§7), this shared test plan, the frozen development handoff and developer's Round 1 notes in the delivery record, and the full implementation under test. Re-ran the developer's focused tests, the full backend regression, and added a new independent test file covering contract rules that the developer's coverage treats only at the codec level or with weaker assertions. Performed static design-contract review of cursor codec, fusion/order, multi-expression pipeline, REST/MCP adapters, runtime principal seam, capability metadata, and config.
- Design-contract review outcome: no Critical/High issues. Confirmed: cursor payload excludes raw query text (§4.6/§6); cursor binds server-derived principal including subject_type, subject_id, actor, principal.project_id, scope, original+normalized queries, filters, mode, depth, limit, context_limit, workspace_versions, source_signatures (§5/§6); fusion order is tier → score → support_count → R1.2-003 tie-breaker and input order is not a key (§4.4); normalized duplicates do not inflate support_count and original list is echoed verbatim (§4.2); `limit` and `context_limit` are independent budgets with independent cursors and section-level truncation flags whose OR feeds the legacy `truncated` field (§4.3/§4.6); `depth=0` yields empty `related_context` and no context cursor; `context_limit=0` with positive depth keeps matches unaffected (§4.5); the shared pipeline resolves scope once and submits one bounded embedding batch (§5); the MCP runtime forwards the refreshed `_authorize_tool` principal through `runtime_principal()` rather than accepting any client-supplied identity (§5/§6); capability metadata exposes canonical `queries`, compatibility `query` alias, defaults/maxes for limit/context_limit/depth, cursor kinds/lifetime/stable-secret flag (§7).

### Independent Round 1 — verification commands and summary lines

- Developer focused tests (re-run independently):
  `cd backend && uv run pytest tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_operation_semantics.py tests/test_semantic_context_cursor.py -x`
  → `68 passed, 60 warnings in 7.03s`.
- Independent tester focused tests (new file):
  `cd backend && uv run pytest tests/test_semantic_context_query_independent.py -v`
  → `13 passed, 3 warnings in 0.55s`. Covers SC-02 (full-pipeline same-Project different-principal cursor fail-closed), SC-08 (ephemeral signer rotation full pipeline), PG-10 (decoded cursor body excludes raw expression), FU-05 (expression-order invariance over identity/score/tier/support/rank), FU-06 (normalized duplicates do not boost support_count; original list echoed verbatim), BD-05 (capability discovery advertises canonical queries, query alias, limit/context_limit/depth defaults+maxes, cursor kinds/lifetime/stable-secret flag; ephemeral fallback advertises limitation), PF-01 (one scope resolution + one embedding batch with queries seen in first-seen order), CX-07 (context_limit=0 with depth=1 keeps matches unaffected), depth=0 (empty related_context, no context cursor), schema mutual-exclusion for queries/query and match_cursor/context_cursor.
- Full backend regression:
  `cd backend && uv run pytest`
  → `785 passed, 6 skipped, 186 warnings in 76.29s` (772 baseline + 13 independent).
- Lint on touched files:
  `cd backend && uv run ruff check tests/test_semantic_context_query_independent.py app/services/semantic_context_query.py app/services/semantic_context_cursor.py app/services/semantic_context_capabilities.py`
  → `All checks passed!`.
- Whitespace:
  `git diff --check`
  → clean.
- Documentation sync:
  `cd backend && uv run pytest tests/test_documentation_sync.py -v`
  → `10 passed, 3 warnings in 6.21s`.

### Independent Round 1 — evidence artifacts

- New independent test file: `backend/tests/test_semantic_context_query_independent.py` (13 tests; absolute path: `/home/yangxiang/projects/ontology-platform/backend/tests/test_semantic_context_query_independent.py`).
- Capability metadata path: `backend/app/services/semantic_context_capabilities.py` (`context_query_capabilities(settings)` → dict advertised via `GET /api/mcp/tools` `capabilities.semantic_context_query`).
- Cursor codec path: `backend/app/services/semantic_context_cursor.py` (versioned HMAC-signed payload; never carries raw query text; uses `semantic_context_query_cursor_signing_secret` when configured and falls back to a process-local ephemeral token).
- Runtime principal seam: `backend/app/mcp/runtime.py` `_authorize_tool` → `_set_runtime_principal` → `runtime_principal()` read by `backend/app/mcp/tools/semantic.py::query_semantic_context`.
- Live service baseline probe (2026-07-20): `curl http://127.0.0.1:8001/api/health` → `{"status":"ok"}`; `curl http://127.0.0.1:8001/api/mcp/tools` → `capabilities.semantic_context_query` is **empty** because the running service is the base commit and the new capability surface is not yet deployed. The runtime-restart verification gate (section 9 item 7) is therefore DEFERRED to the main agent's commit+restart step.

### Independent Round 1 — conclusion

Independent tester returns **PASS-with-DEFERRED** for the unit-testable contract surface of R1.2-004. The implementation honors the frozen design contract at every check the tester could cover without live PostgreSQL + pgvector + Oxigraph and without a service restart. No Critical/High defects. The remaining cases require live infrastructure and a service restart and are explicitly out of scope for this independent tester per the dispatch instructions; the main agent should arrange them as a follow-up runtime round before flipping R1.2-004 to `已实现`.
