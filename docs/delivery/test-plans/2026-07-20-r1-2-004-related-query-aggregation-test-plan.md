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
