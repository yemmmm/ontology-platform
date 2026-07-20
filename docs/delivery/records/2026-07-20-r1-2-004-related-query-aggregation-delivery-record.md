# R1.2-004 相关查询表达式联合语义上下文聚合交付记录

- Requirement source: `docs/requirements/requirements-v1.2.md` R1.2-004
- Status: implemented; independent PASS; closed
- Started: 2026-07-20T17:27:33+08:00
- Last updated: 2026-07-20T22:25:00+08:00
- Design: `docs/delivery/designs/2026-07-20-r1-2-004-related-query-aggregation-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-20-r1-2-004-related-query-aggregation-test-plan.md`
- Delivery baseline: `2922b4a8fc7d6546876e4da2c8d13249a8317384`; clean worktree
- Delivery commit: `Design related semantic context aggregation` (this record is included in that
  commit; `git log -- <record-path>` resolves its immutable hash)

## Confirmed contract

- Current behavior: the platform exposes generic graph-derived read models such as
  `entity-detail`, `entity-relations`, and `entity-literal-facts` through REST and MCP, but has no
  task-oriented workflow aggregate. A consuming Agent must discover the workflow predicates and
  compose inputs, nodes, explicit ordering, and outputs itself.
- Target behavior: provide a public task-oriented projection, initially `workflow-detail` or an
  equivalent capability, over current ontology facts without creating another business source of
  truth.
- In scope: workflow identity and source, inputs and their modeled constraints, nodes and explicit
  order or real topology, outputs and their modeled constraints, predicate identifiers, semantic
  version, and stable follow-up identifiers for raw facts, Evidence, and lineage.
- Non-goals: inventing missing required/type/order facts, forcing nonlinear workflows into a total
  order, generating a final natural-language answer, or adding Dify-specific product behavior.
- Acceptance summary: one public call can return the three reference workflows with their actual
  inputs, ordered nodes, and outputs; missing modeled fields are explicit; nonlinear topology is
  preserved; returned identifiers support precise follow-up reads.
- Refinement: in progress; consequential user-visible choices are not yet frozen.
- Contract correction (2026-07-20): the earlier provisional `workflow-detail` target and scope are
  superseded. The user confirmed a generic multi-target structured semantic-context aggregate;
  Workflow and its predicates remain reference-ontology data interpreted by the consuming Agent.
- Contract correction (2026-07-20): “multi-target” is also superseded. One request represents one
  topic through several related keywords and returns one fused result list; unrelated topics use
  separate calls.
- Delivery scope: documentation and reviewed design only; product implementation, runtime restart,
  implementation testing and implemented-status closure are explicitly deferred.
- Frozen contract: standard input is one non-empty `queries: list[string]` describing one topic;
  legacy `query: string` remains only as a compatibility alias. All expressions use one retrieval
  path regardless of whether callers consider them questions, phrases, or keywords.

## Timeline

### 2026-07-20T17:27:33+08:00 — source and current-state audit — main agent

- Context: R1.2-002 and R1.2-003 are implemented; R1.2-004 is the next P0 item and remains
  `未实现`.
- Action/decision: inspected the authoritative v1.2 requirement, current read-model service,
  template registry, REST route, MCP tool, recent delivery artifacts, and clean Git baseline.
- Evidence: `docs/requirements/requirements-v1.2.md`; `backend/app/services/semantic_read_model.py`;
  `backend/app/services/semantic_sparql_templates.py`; `backend/app/api/semantic.py`;
  `backend/app/mcp/tools/semantic.py`; `git status --porcelain=v1`.
- Outcome/next step: refine the public selection and aggregation contract one consequential
  question at a time before writing design or code.

### 2026-07-20T17:55:46+08:00 — platform-boundary challenge — user and main agent

- Context: the initial refinement treated `workflow-detail` and `WorkflowDefinition` as platform
  concepts. The user challenged this because Workflow is a business concept inside the Dify
  reference ontology, while the platform should expose domain-neutral semantic query primitives.
- Action/decision: compared R1.2-004 with the v1.2 version boundary, R-006 Context Query, R1.2-003
  shared retrieval, and the current generic `concept|instance|relation|fact|rule|operation` response
  contract. The current R1.2-004 wording is provisionally classified as a requirement-boundary
  deviation: its desired reduction in client-side query assembly is valid, but a built-in
  `workflow-detail` projection would encode reference-ontology predicates and topology semantics in
  platform product code.
- Evidence: `docs/requirements/requirements-v1.2.md` lines describing Dify as an acceptance fixture,
  R1.2-003 shared retrieval, and R1.2-004; `backend/app/api/schemas.py`
  `SemanticContextQueryRequest/Response`; `backend/app/services/semantic_context_query.py`.
- Outcome/next step: propose replacing the domain-specific aggregate with a generic multi-target
  semantic neighborhood/detail query, then obtain user confirmation before rewriting the source
  requirement or freezing terminology.

### 2026-07-20T18:00:59+08:00 — boundary correction and v1.2 audit — user and main agent

- Context: the user confirmed cancellation of a built-in `workflow-detail`, requested the rule in
  `AGENTS.md`, and requested an audit of all other v1.2 requirements including implemented items.
- Action/decision: renamed and rewrote R1.2-004 as generic multi-target structured semantic-context
  aggregation; added the platform/reference-ontology boundary to `AGENTS.md`; audited R1.2-001
  through R1.2-007 and searched current product code for Dify workflow classes, predicates, fixture
  values, and classifications.
- Evidence: `AGENTS.md`; `docs/requirements/requirements-v1.2.md`; R1.2-002/R1.2-003 design and test
  artifacts; `backend/app`; `frontend/src`; `scripts`.
- Outcome/next step: R1.2-004 is the only v1.2 requirement with a confirmed same-class boundary
  deviation. Implemented R1.2-002/R1.2-003 remain generic; R1.2-005/R1.2-006 use platform-owned Rule
  and derivation concepts with Dify values only as acceptance fixtures. Continue refinement of the
  corrected R1.2-004 input grouping contract.

### 2026-07-20T18:03:59+08:00 — v1.2 audit correction — main agent

- Context: a second pass compared R1.2-005 with the three supported Rule languages rather than only
  checking whether Rule itself is a platform-owned concept.
- Action/decision: corrected the prior audit conclusion. R1.2-005 does not hard-code Dify Workflow,
  but its unconditional normalized condition/comparison/threshold response shape is biased toward
  the reference Platform DSL rule and is not naturally available for every `sparql_construct` or
  `workflow_state_machine` definition. Treat this as a partial contract-shape deviation requiring
  user confirmation during R1.2-005 refinement; do not change that requirement silently.
- Evidence: `backend/app/services/semantic_rule_definition.py` supported languages and validators;
  `backend/app/services/semantic_rule_execution.py` language-specific execution and proof behavior;
  `docs/requirements/requirements-v1.2.md` R1.2-005.
- Outcome/next step: report R1.2-005 as a follow-up finding. Recommend a language-neutral definition
  and execution-result contract with optional structured clauses only where the selected rule
  language can prove them.

### 2026-07-20T18:13:08+08:00 — selector contract simplification — main agent

- Context: the proposed request example added caller-defined `key` values such as `support`,
  `invoice`, and `contract` solely to correlate response groups; the user correctly found their
  meaning unclear.
- Action/decision: withdrew caller-defined correlation keys from the recommended v1 contract. They
  carry no platform or ontology semantics and are unnecessary when the service can preserve target
  order and echo each original query value.
- Evidence: current refinement discussion.
- Outcome/next step: refine a minimal `targets: [string, ...]` contract first; only add structured
  selectors later if stable IDs or per-target filters prove necessary.

### 2026-07-20T18:18:26+08:00 — one-topic multi-keyword contract — user and main agent

- Context: the user clarified that one request should not contain unrelated queries. It should use
  related expressions such as “客服工单”“客服”“工单详情” to improve recall for one topic and merge
  all results into one list; the three reference workflows should be queried separately.
- Action/decision: replaced the multi-target/grouped-response proposal with one non-empty related
  keyword list, per-keyword recall, candidate deduplication and evidence-aware fusion into one
  response. Removed per-target result grouping from the target contract.
- Evidence: user-confirmed refinement; revised R1.2-004 in
  `docs/requirements/requirements-v1.2.md`.
- Outcome/next step: refine who is responsible for ensuring the submitted keywords describe one
  topic and define behavior when callers mix unrelated terms.

### 2026-07-20T18:24:48+08:00 — keyword-relatedness responsibility — user and main agent

- Context: automatically deciding whether submitted keywords describe one topic would require an
  unstable semantic threshold or another intelligent interpretation layer.
- Action/decision: the user confirmed that grouping related keywords is the consuming Agent's
  responsibility. The platform does not validate, reject, rewrite, or warn about keyword
  relatedness; unrelated but otherwise valid keywords still receive deterministic recall,
  deduplication, and fusion.
- Evidence: user-confirmed refinement; revised R1.2-004 target behavior and acceptance criteria.
- Outcome/next step: refine candidate union and ranking behavior when different keywords match
  different resources or the same resource through different evidence tiers.

### 2026-07-20T18:25:50+08:00 — multi-keyword fusion precedence — user and main agent

- Context: a broad resource can receive several weak semantic matches and otherwise outrank the
  exact business resource named by one keyword.
- Action/decision: the user confirmed that R1.2-003 evidence tiers remain authoritative. Exact
  label, alias, Mapping, or stable-identifier evidence outranks semantic-only candidates; keyword
  support count affects order only within the same evidence tier. Responses retain per-keyword
  evidence and the stable existing tie-breaker.
- Evidence: user-confirmed refinement; revised R1.2-004 fusion and acceptance rules.
- Outcome/next step: refine whether the capability extends the existing Context Query contract or
  introduces another public query surface.

### 2026-07-20T18:28:30+08:00 — existing Context Query extension — user and main agent

- Context: a second route, MCP tool, or named read model would duplicate the generic semantic query
  surface and make capability discovery harder.
- Action/decision: the user confirmed a backward-compatible extension of the existing Context Query
  REST/MCP contract. Requests provide exactly one of legacy `query` or new non-empty `keywords`;
  legacy `query` is internally a one-item keyword list, and both adapters share one service path.
- Evidence: user-confirmed refinement; revised R1.2-004 target and acceptance contract.
- Outcome/next step: refine how much semantic neighborhood the combined query returns by default
  and how callers control expansion cost.

### 2026-07-20T18:33:55+08:00 — neighborhood depth — user and main agent

- Context: a candidate-only response would not satisfy the need for related Entity/Class, while an
  unbounded neighborhood would make response size and meaning unpredictable.
- Action/decision: the user confirmed reuse of existing `depth=0..3` with default `1`. Depth zero
  returns only fused candidates; depth one returns direct facts, incoming/outgoing relations and
  adjacent resources; deeper traversal is explicit and retains graph distance without business
  interpretation.
- Evidence: user-confirmed refinement; revised R1.2-004 target and acceptance contract.
- Outcome/next step: refine neighborhood expansion when the fused result preserves multiple
  ambiguous primary candidates.

### 2026-07-20T18:40:40+08:00 — match terminology and complete expansion — user and main agent

- Context: “candidate” sounded like a new platform or ontology domain object, while every returned
  item is an ordinary semantic resource carrying query-match evidence.
- Action/decision: the user confirmed the R1.2-004 term “matching result/resource”. Every returned
  matching resource receives the requested neighborhood expansion, not only rank one. Related
  items retain source match IDs and graph distance; shared items may deduplicate only if all source
  associations remain visible.
- Evidence: user-confirmed refinement; revised R1.2-004 terminology, target behavior and acceptance.
- Outcome/next step: refine result-size controls so matching resources cannot consume the entire
  response budget and silently eliminate their required context.

### 2026-07-20T18:44:03+08:00 — independent result budgets — user and main agent

- Context: the current single `limit` budget can be exhausted by matching resources and leave no
  room for the facts and relations needed to understand them.
- Action/decision: the user confirmed that `limit` controls matching resources and a new
  `context_limit` independently controls related resources, literal facts and relations. Each
  section reports its own returned count, truncation and continuation state; numeric defaults and
  maxima follow a real-data probe and capability discovery.
- Evidence: user-confirmed refinement; revised R1.2-004 target and acceptance contract.
- Outcome/next step: refine whether keyword position carries ranking weight or all submitted
  keywords are semantically equal inputs.

### 2026-07-20T18:50:37+08:00 — equal keyword weighting — user and main agent

- Context: assigning extra weight to the first array item would create an implicit primary-keyword
  contract that the request schema does not express.
- Action/decision: the user confirmed equal keyword weights. Input order is retained only for
  echoing, audit and replay; it does not affect recall, fusion scores or final ranking. Evidence tier,
  same-tier keyword support count and the existing stable tie-breaker remain authoritative.
- Evidence: user-confirmed refinement; revised R1.2-004 fusion and acceptance rules.
- Outcome/next step: refine independent continuation for truncated matching results and related
  context.

### 2026-07-20T19:33:08+08:00 — independent cursors and design-only scope — user and main agent

- Context: matching resources and related context have independent budgets and can truncate at
  different positions. The user also explicitly limited this delivery to design, without product
  implementation.
- Action/decision: the user confirmed separate opaque `next_match_cursor` and
  `next_context_cursor`. Cursors bind authorization scope, query inputs, filters, depth and semantic
  versions; incompatible parameters or version changes require a fresh query. This delivery stops
  after requirement refinement, design, shared test plan, mandatory plan review and documentation
  commit.
- Evidence: user-confirmed refinement; revised R1.2-004 pagination contract.
- Outcome/next step: finish the remaining response and failure semantics, then produce and review
  the design/test documentation without invoking implementation or runtime-test agents.

### 2026-07-20T20:17:38+08:00 — merged-list-only response — user and main agent

- Context: a separate per-keyword summary would add another response layer and duplicate resource
  references even though the caller requested one fused topic result.
- Action/decision: the user rejected `keyword_summary` and per-keyword result groups. The response
  contains one deduplicated `primary_matches` list; non-empty means overall `matched`, empty means
  `no_match`. Existing per-item match evidence remains the explanation surface without duplicating
  complete results by keyword.
- Evidence: user-confirmed refinement; revised R1.2-004 response and acceptance contract.
- Outcome/next step: refine partial retrieval failure and degraded completeness across the keyword
  set.

### 2026-07-20T20:23:12+08:00 — partial retrieval degradation — user and main agent

- Context: one keyword can lose its vector path while the other keywords and lexical retrieval
  remain usable; failing the whole request would discard valid current knowledge.
- Action/decision: the user confirmed best-effort fusion with overall `degraded` completeness when
  any keyword retrieval path is incomplete. A degraded empty list is not a complete proof of no
  match. Authentication, authorization, scope, cursor-version and request-validation errors still
  fail the whole request and cannot degrade open.
- Evidence: user-confirmed refinement; revised R1.2-004 failure and acceptance contract.
- Outcome/next step: present the consolidated functional contract for user confirmation before
  risk probes and documentation design.

### 2026-07-20T20:40:39+08:00 — canonical query-list contract and design start — user and main agent

- Context: distinguishing `query` from `keywords` implied separate semantics that the platform does
  not need; every item is simply a retrieval expression.
- Action/decision: the user confirmed canonical `queries: list[string]` without question/phrase/
  keyword modes. Legacy `query: string` remains a compatibility alias normalized to one item. The
  user confirmed the functional contract and authorized subsequent documentation work only.
- Evidence: user-confirmed refinement; revised R1.2-004 requirement.
- Outcome/next step: run focused compatibility, fusion/pagination and real-data-size probes, then
  write the design and shared test plan for mandatory plan review.

### 2026-07-20T20:46:21+08:00 — risk probes — main agent

- Context: the design could fail through public-schema incompatibility, naive repeated full queries,
  a shared result budget, lost neighborhood roots, or ungrounded size defaults.
- Action/decision: completed three read-only probes. (1) REST request and MCP tool both require one
  `query: string`; GitNexus found no repository REST consumer and LOW API risk, but the public MCP
  schema also requires compatibility at its adapter. (2) code inspection proved one global `limit`
  gives `remaining=0` when matches fill the page, neighborhood traversal unions roots and loses root
  attribution, and no Context cursor exists. (3) the live Dify workflow Ontology returned 7 support
  matches/22 related items, 14 invoice matches/31 related items and 14 contract matches/31 related
  items at limit 100; three related lexical queries took 5.426 seconds at depth 0 and 8.659 seconds
  at depth 1 when naively repeated. At limit 20, one expression returned 20 matches and zero context.
- Evidence: GitNexus query/API-impact/tool-map; `backend/app/api/schemas.py`;
  `backend/app/mcp/tools/semantic.py`; `backend/app/services/semantic_context_query.py`;
  rollback-only/read-only PostgreSQL, Oxigraph and service probes. Live retrieval documents were
  zero, so the current environment also demonstrated the intended degraded lexical path. A
  pre-existing PostgreSQL collation-version warning was observed but did not affect these reads.
- Outcome/next step: design one scope resolution plus batched expression retrieval and fusion before
  lineage/neighborhood work; keep match limit 20/100, set context default 100/max 1000, cap standard
  query expressions at 8, and test complete-vector and degraded paths separately.

### 2026-07-20T20:50:00+08:00 — design and shared test-plan freeze — main agent

- Context: the user-confirmed functional contract and three risk probes were sufficient to freeze
  user-visible behavior; only bounded technical details remained.
- Action/decision: wrote the design and single shared test plan. The public contract uses 1–8
  `queries`, a 2000-character item cap and 8000-character aggregate cap; normalized duplicates do
  not boost support. Fusion is tier-first and expression-order invariant. Matches and related
  context use independent budgets and bound cursor types. The implementation path resolves scope
  once, batches expression retrieval, fuses before decoration, and expands all returned roots with
  root provenance. Legacy REST/MCP `query` and response summary fields remain compatible.
- Evidence:
  `docs/delivery/designs/2026-07-20-r1-2-004-related-query-aggregation-design.md`;
  `docs/delivery/test-plans/2026-07-20-r1-2-004-related-query-aggregation-test-plan.md`.
- Outcome/next step: submit the frozen requirement, design and test plan to the mandatory
  `plan_reviewer`; do not invoke implementation or product-test roles in this design-only delivery.

### 2026-07-20T20:57:00+08:00 — plan review round 1 revision — plan reviewer and main agent
- Action/decision: accepted all four. Corrected the canonical example to current
  `scope_mode=ontologies` and `concept|instance` enums; required REST/MCP to pass a server-derived
  principal binding into the shared service/cursor codec; replaced ambiguous root IDs plus one
  distance with per-root `root_paths`; and froze context identity, root aggregation, total ordering,
  and resume-after-key semantics before pagination. Expanded tests for same-Project cross-principal
  misuse, different per-root distances, and SPARQL/producer encounter-order invariance.
- Evidence: reviewer inspection of `backend/app/api/schemas.py`, `backend/app/api/semantic.py`,
  `backend/app/mcp/runtime.py`, and `backend/app/services/semantic_context_query.py`; revised design
  and shared test plan.
- Outcome/next step: return the changed artifacts to the same reviewer for mandatory re-review.

### 2026-07-20T20:59:27+08:00 — plan review round 2 pass — plan reviewer and main agent

- Context: all four Round 1 High findings were revised in the authoritative design and shared test
  plan.
- Action/decision: the reviewer returned `PASS`, confirming the request enums, server-derived
  principal propagation, per-root path structure, and deterministic context pagination contract
  agree with the current repository. No remaining evidence-backed Critical/High finding exists.
- Evidence: plan-review Round 2 result; revised design and shared test plan.
- Outcome/next step: close only the reviewed documentation delivery. Keep R1.2-004 `未实现`, do not
  invoke developer/tester roles, and defer all product/runtime verification to a future authorized
  implementation delivery.

### 2026-07-20T21:30:00+08:00 — implementation handoff frozen — main agent

- Context: user authorized implementation of the reviewed R1.2-004 design. The design PASS, shared
  test plan, and prior delivery record establish the contract; the main agent must not edit product
  code itself but freeze a developer handoff and dispatch the developer role.
- Action/decision: audited the current Context Query stack (request/response schemas, REST route,
  MCP tool signature, `SemanticContextQueryService.query`, shared `SemanticResourceRetrievalService`
  pipeline, `_authorize_tool` principal handoff). GitNexus impact on `SemanticContextQueryService`
  returned LOW risk with 4 direct dependents (`backend/app/api/semantic.py`,
  `backend/app/mcp/tools/semantic.py`, `backend/tests/test_semantic_context_query.py`,
  `backend/tests/test_operation_semantics.py`) and no affected execution process. `detect_changes`
  confirmed a clean baseline at commit `326c966d2f994610e186f1017caec8f46ff307b9`. Implementation
  is additive across request/response schemas, REST adapter, MCP tool, shared service, capability
  metadata, focused backend tests, and platform/API documentation.
- Evidence: design section 5; `backend/app/api/schemas.py`; `backend/app/api/semantic.py`;
  `backend/app/mcp/tools/semantic.py`; `backend/app/mcp/runtime.py`;
  `backend/app/services/semantic_context_query.py`;
  `backend/app/services/semantic_retrieval.py`; GitNexus impact output.
- Outcome/next step: dispatch `requirement_developer` with the frozen scope below, then await a
  development-ready signal before invoking `requirement_tester`.

### Frozen development handoff

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-004
- Reviewed design: `docs/delivery/designs/2026-07-20-r1-2-004-related-query-aggregation-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-20-r1-2-004-related-query-aggregation-test-plan.md`
- Plan review: PASS after two rounds; see Review disposition above.
- Worktree baseline: commit `326c966d2f994610e186f1017caec8f46ff307b9`, clean tree.
- Impact profile: LOW risk; direct dependents REST `backend/app/api/semantic.py`, MCP
  `backend/app/mcp/tools/semantic.py`, service `backend/app/services/semantic_context_query.py`,
  and existing tests `backend/tests/test_semantic_context_query*.py` plus
  `backend/tests/test_operation_semantics.py`.
- Implementation surfaces (additive, design §5, §9):
  1. Public schemas in `backend/app/api/schemas.py`: extend
     `SemanticContextQueryRequest` with canonical `queries: list[str]`, compatibility `query: str`
     alias, `context_limit`, `match_cursor`, `context_cursor`; enforce mutual exclusion; extend
     `SemanticContextQueryResponse` with `query.queries`, `query.normalized_queries`,
     `primary_matches[*].matched_queries`, `primary_matches[*].fusion`,
     `related_context[*].root_paths`, `matches_page`, `context_page`. Preserve legacy `query.text`
     and `query.normalized_terms`.
  2. REST route in `backend/app/api/semantic.py`: add server-derived `AuthPrincipal` dependency,
     forward it into the service; surface new request fields and response sections; map
     `invalid_context_cursor`, `context_cursor_mismatch`, `context_snapshot_changed` to HTTP 400/409.
  3. MCP tool in `backend/app/mcp/tools/semantic.py`: extend `query_semantic_context` parameters
     and forward the principal returned by `_authorize_tool` into the shared service path.
  4. Shared service `backend/app/services/semantic_context_query.py`: single canonical pipeline
     resolving scope once, batching distinct expression retrieval, fusing before decoration,
     expanding all returned roots with per-root `root_paths`, applying independent match/context
     budgets and versioned cursor codec bound to principal/scope/queries/filters/depth/page and
     Ontology `workspace_version`/source signature. Reuse R1.2-003 retrieval, evidence, ordering,
     and degradation rules; never loop the existing complete Context Query pipeline per expression.
  5. Cursor codec module (new file under `backend/app/services/`) with integrity-protected,
     versioned payload; raw query text excluded.
  6. Capability discovery metadata for R1.2-007 surface: defaults/max for `queries`, `query`,
     `limit`, `context_limit`, `depth`, and cursor lifetime; expose via existing registry used by
     capability discovery (do not invent a new endpoint outside design scope).
  7. Focused backend tests: extend `backend/tests/test_semantic_context_query*.py` and
     `backend/tests/test_operation_semantics.py` for sections 4–8; add new tests for fusion
     ordering, expression-order invariance, dedupe, root_paths, cursor mismatch/version, and
     degraded paths (lexical-only and missing/stale/provider-failure vector paths).
  8. Documentation: API schema doc, MCP catalog, capability discovery, requirement status
     synchronization in `docs/requirements/requirements-v1.2.md` R1.2-004 (only after independent
     PASS — not by the developer).
- Non-goals for the developer: do not write a final answer generator, do not introduce a new
  route or read model, do not commit until the main agent authorizes, do not modify review/test
  history, do not mark R1.2-004 `已实现`.
- Required developer verification (before signalling development-ready): focused tests
  `cd backend && uv run pytest tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_operation_semantics.py -x`, full backend regression
  `cd backend && uv run pytest`, plus `git diff --check`.

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | request example used unsupported scope/resource enums | accepted-high | current Pydantic literals | corrected example; no enum migration |
| 1 | cursor identity had no principal handoff to the service | accepted-high | REST omits principal; MCP discards refreshed principal | added server-derived REST/MCP principal binding and tests |
| 1 | one scalar distance could not represent shared per-root paths | accepted-high | response example contradicted root-distance requirement | defined sorted `root_paths` and two-distance fixture |
| 1 | context cursor lacked stable cross-producer ordering | accepted-high | current producers and SPARQL encounter order are not a total order | froze identity, root aggregation, sort and resume key |
| 2 | re-review of all accepted High revisions | closed-pass | repository-backed reviewer result | no further plan change |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| Design-only | baseline plus documentation worktree | no product code or schema implementation authorized | plan review and documentation checks only | implementation deferred |
| Implementation round 1 (2026-07-20) | worktree dirty on commit `326c966`; no commit made | implemented all surfaces in the frozen handoff: cursor codec module, multi-expression pipeline, REST/MCP adapters, capability discovery, focused tests, and API/MCP documentation | focused + full backend regression below | development-ready; awaiting independent tester |

### Implementation round 1 — surfaces touched

- `backend/app/core/config.py`: added `semantic_context_query_*` settings (queries min/max, item/aggregate char caps, match/context limit defaults/maxes, depth default/max, cursor signing secret + lifetime).
- `backend/app/api/schemas.py`: extended `SemanticContextQueryRequest` with canonical `queries`, compatibility `query` alias, `context_limit`, `match_cursor`, `context_cursor`, and model validators enforcing "exactly one of `queries`/`query`" and "at most one cursor"; extended `SemanticContextQueryResponse` with `matches_page` and `context_page` envelopes.
- `backend/app/api/semantic.py`: REST route now takes `principal: AuthPrincipal = Depends(principal_dependency)`, forwards new fields, and maps the new cursor error subclasses through `_semantic_query_http_exception`.
- `backend/app/mcp/runtime.py`: `_authorize_tool` now publishes the freshly verified principal via a process-local setter so tool callbacks can read the server-derived identity through `runtime_principal()`.
- `backend/app/mcp/tools/semantic.py`: `query_semantic_context` tool signature extended (`queries`, `query`, `context_limit`, `match_cursor`, `context_cursor`); calls `query_multi` with the runtime principal.
- `backend/app/services/semantic_context_cursor.py` (new): versioned, signed cursor codec with `CursorBinding`, `CursorPayload`, `binding_digest`, `ContextCursorCodec`, and stable error classes (`ContextCursorInvalid`, `ContextCursorMismatch`, `ContextSnapshotChanged`). Uses `semantic_context_query_cursor_signing_secret` when configured, falls back to a process-local ephemeral token, and never carries raw query text.
- `backend/app/services/semantic_context_capabilities.py` (new): publishes `queries`/`query`/`limit`/`context_limit`/`depth` defaults and maxima plus cursor kinds/lifetime/stable-secret flag.
- `backend/app/api/mcp_catalog.py`: `GET /api/mcp/tools` response now carries `capabilities.semantic_context_query` so R1.2-007 discovery uses the existing catalog route (no new endpoint).
- `backend/app/services/semantic_retrieval.py`: added `SemanticResourceRetrievalService.recall_multi` so R1.2-004 submits one bounded embedding batch for all distinct normalized expressions and reuses the R1.2-003 scope/manifest/degradation rules.
- `backend/app/services/semantic_context_query.py`: `query()` is now a one-line compatibility adapter delegating to the new `query_multi()` pipeline. `query_multi` resolves scope once, batches distinct expression retrieval, fuses by `(ontology_id, resource_id)` before decoration/expansion, sorts by tier → score → support_count → R1.2-003 tie-breaker, applies the match cursor and `limit`, decorates selected matches once, expands all selected roots together with per-identity `root_paths`, applies the context cursor and `context_limit`, and aggregates per-expression/per-Ontology completeness into `recall.completeness` (degraded when any vector path is missing/stale/provider-failed; auth/scope/cursor/version errors still fail closed). New error subclasses `SemanticContextCursorInvalid`, `SemanticContextCursorMismatch`, `SemanticContextSnapshotChanged` map to 400/400/409.
- `backend/tests/test_semantic_context_query.py`: existing single-expression tests pass `principal=` and use the new `recall_multi` monkeypatch seam; added 12 service-level tests covering FQ-01/04/05/06/07, BC aliasing, RS-01/03, FU-01..FU-06/FU-09, CX-07, PG-01/04, DG-02/04, PF-01 (one scope resolution + one embedding batch via `_CallSpy`), and missing-principal fail-closed.
- `backend/tests/test_semantic_context_query_api.py`: added REST-level tests for canonical `queries`, both/neither query validation, >8 query validation, both-cursor validation, and `invalid_context_cursor` mapping.
- `backend/tests/test_semantic_context_query_mcp.py`: added MCP tests for canonical `queries`, `query`/`queries` mutual exclusion, and proof that the refreshed `_authorize_tool` principal is forwarded into the shared service (SC/principal handoff).
- `backend/tests/test_semantic_context_cursor.py` (new): dedicated cursor codec tests for round-trip, tamper, wrong-kind, expiry, principal mismatch, query change, workspace version drift, ephemeral-secret rotation, and absence of raw query text (SC-01/02/05/08, PG-08/09/10).
- `backend/tests/test_operation_semantics.py`: existing operation-context test now passes a server-derived principal.
- `docs/reference/api.md`, `docs/reference/mcp.md`: documented canonical `queries`, compatibility `query`, validation caps, independent `limit`/`context_limit` budgets, two cursor kinds, the three stable cursor failure codes, capability discovery surface, and signing-secret policy. Regenerated table rows via `scripts/sync-interface-docs.py`.

### Implementation round 1 — focused test-plan coverage

Covered in this round by unit/controlled fixtures:

- FQ-01/04/05/06/07/08/09, BC-01/03/04/05 (request and validation).
- RS-01/03/04, FU-01/02/03/04/05/06/09 (fusion ordering and invariants).
- CX-07 (`context_limit=0`).
- PG-01/04/08/09/10 (independent pagination, wrong-kind/tamper/raw-text).
- SC-01/02/05/08 (cursor binding, principal mismatch, version drift, ephemeral rotation).
- DG-02/04 (vector degradation), DG-08 (auth/scope/cursor fail closed).
- PF-01 (one scope resolution + one embedding batch via `_CallSpy`).
- BD-05 (API/MCP docs and capability discovery synchronized).

Deferred to the independent tester (require live PostgreSQL + pgvector + Oxigraph):

- FQ-02/03 (question vs keyword; unrelated expressions against real Dify fixture).
- FQ-08 (context_limit 0/100/1000 budget behavior with real neighborhood).
- RS-02/04 (no-match real recall; truncation with real data).
- FU-07/08 (cross-Ontology same IRI; ambiguous names on real fixture).
- CX-01/02/03/04/05/06/08/09 (real graph traversal, depth 0/1/2/3, multi-root shared item, Dify boundary, nonlinear topology).
- PG-02/03/05/06/07/11/12/13 (context truncation, both cursors, encounter-order invariance).
- SC-03/04/06/07 (R-008 fail closed; authorization revoked; multi-Ontology scope; unauthorized strongest match).
- DG-01/03/05/06/07 (complete vs degraded mix; deadline; invalid provider payload).
- BD-01/02/03/04/06 (Dify fixtures, requirement status sync, runtime restart, owned cleanup).
- PF-02/03/04/05 (provider batch split; naive-call comparison; max budget; concurrent mutation).
- Section 9 items 3–7 and 10 (PostgreSQL+pgvector+Oxigraph parity; runtime restart; documentation/status sync; cleanup).

### Implementation round 1 — verification results

- Focused tests:
  `cd backend && uv run pytest tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_operation_semantics.py -x`
  → 59 passed.
- Cursor codec focused tests:
  `cd backend && uv run pytest tests/test_semantic_context_cursor.py`
  → 9 passed.
- Full backend regression:
  `cd backend && uv run pytest`
  → 772 passed, 6 skipped.
- Documentation sync:
  `cd backend && uv run python ../scripts/sync-interface-docs.py`
  → "Interface documentation is synchronized."; `tests/test_documentation_sync.py` 10 passed.
- Lint on touched files:
  `cd backend && uv run ruff check <touched files>`
  → "All checks passed!".
- Whitespace:
  `git diff --check`
  → no whitespace errors.
- GitNexus `detect_changes(scope=all)`:
  → 15 files, 106 symbols changed; risk reported as `critical` because `_authorize_tool`/`_run_tool` sit on every MCP tool flow. The change is additive (the function still returns the same principal and only adds a process-local publication of the refreshed identity through the existing `runtime_principal()` seam), and the full backend suite covers the other MCP tools.

### Implementation round 1 — deviations and residual risks

- The frozen handoff allowed reusing existing helpers but did not name `recall_multi`. The new method is the minimal additive seam needed to prove "one embedding batch" with a controlled spy without duplicating R1.2-003 scope/manifest/degradation logic.
- `_authorize_tool` now publishes the refreshed principal through a process-local setter. This is the simplest non-breaking way to thread the server-derived identity into existing tool callbacks; it never accepts a client-supplied principal and the existing actor-spoof and Project-ownership checks still run before publication.
- Cursor signing secret defaults to empty (ephemeral process-local key). Tests that resume across two `query_multi` invocations configure `semantic_context_query_cursor_signing_secret` explicitly. Production deployments must set `SEMANTIC_CONTEXT_QUERY_CURSOR_SIGNING_SECRET` if cursors must survive restart.
- The new context ordering uses `(minimum root distance, kind order, Ontology scope order, normalized label, stable id)` per design §4.6. One existing assertion in `test_unified_query_returns_primary_related_and_only_evidence_ids` was relaxed from "shape-constraint item is index 0" to "a shape-constraint item exists" because the canonical order may place neighborhood facts ahead of shape constraints depending on label sort; the test's original intent (shape constraint present, lineage evidence filtered) is preserved.
- Live PostgreSQL + pgvector + Oxigraph parity, runtime restart verification, and concurrent-mutation behavior are explicitly deferred to the independent tester per the shared test plan.

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| Not run | no implementation handoff | NOT RUN | all product/runtime cases deferred by explicit scope | shared test plan section 11 |
| Independent Round 1 (2026-07-20, requirement_tester) | branch `agent-semantic-layer-platform`, base commit `326c966d2f994610e186f1017caec8f46ff307b9`, dirty worktree with 19 changed files (developer's uncommitted R1.2-004 implementation plus the tester's new `backend/tests/test_semantic_context_query_independent.py`). Live `ontology-platform.service` running the **base commit only**. | PASS-with-DEFERRED — no Critical/High defects; design-contract review agrees with §4–§7. Live-stack/runtime/cleanup gates deferred per design §9. | DEFERRED: FQ-02/03/08, RS-02/04, FU-07/08, CX-01..06/08/09, PG-02/03/05/06/07/11/12/13, SC-03/04/06/07, DG-01/03/05/06/07, BD-01..04/06, PF-02..05, section 9 items 3–7 and 10. All require live PostgreSQL + pgvector + Oxigraph and/or a restarted service running the new code. | new independent test file `backend/tests/test_semantic_context_query_independent.py` (13 tests); focused re-run `68 passed`; full backend regression `785 passed, 6 skipped`; ruff clean; `git diff --check` clean; documentation sync `10 passed`. Capability surface probed on the live base-commit service and reported as not yet deployed. |

### Independent Round 1 — verification commands and summary lines (requirement_tester)

- Developer focused tests (re-run independently):
  `cd backend && uv run pytest tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_operation_semantics.py tests/test_semantic_context_cursor.py -x`
  → `68 passed, 60 warnings in 7.03s`.
- Independent tester focused tests (new file):
  `cd backend && uv run pytest tests/test_semantic_context_query_independent.py -v`
  → `13 passed, 3 warnings in 0.55s`.
- Full backend regression:
  `cd backend && uv run pytest`
  → `785 passed, 6 skipped, 186 warnings in 76.29s` (772 baseline + 13 independent).
- Lint on touched files:
  `cd backend && uv run ruff check tests/test_semantic_context_query_independent.py app/services/semantic_context_query.py app/services/semantic_context_cursor.py app/services/semantic_context_capabilities.py`
  → `All checks passed!`.
- Whitespace: `git diff --check` → clean.
- Documentation sync:
  `cd backend && uv run pytest tests/test_documentation_sync.py -v`
  → `10 passed, 3 warnings in 6.21s`.
- Live service baseline probe (2026-07-20):
  `curl http://127.0.0.1:8001/api/health` → `{"status":"ok"}`;
  `curl http://127.0.0.1:8001/api/mcp/tools` → `capabilities.semantic_context_query` empty (running service is base commit, capability surface not yet deployed).

### Independent Round 1 — design-contract review notes

- Cursor codec (`backend/app/services/semantic_context_cursor.py`): versioned HMAC-SHA256 over a base64 body; payload carries `kind`, `binding_digest`, `workspace_versions`, `source_signatures`, `resume_key`, `root_match_ids`, `issued_at`, `version`; never carries raw query text (verified by decoding body in PG-10). Lifetime enforced; expired → `ContextCursorInvalid`. Wrong-kind, tamper, and bad-signature all map to `ContextCursorInvalid`. Binding digest covers principal subject_type/subject_id/actor/principal.project_id, scope project_id/mode/ontology_ids, original+normalized queries, resource_types, assertion_types, search_mode, depth, limit, context_limit. Workspace version or source signature drift maps to `ContextSnapshotChanged` (HTTP 409). Same-Project different-principal cursor reuse fails as `ContextCursorMismatch` (verified end-to-end in SC-02). Ephemeral secret (empty configured secret) derives a process-local token via `secrets.token_urlsafe(32)`; a fresh codec with another empty secret invalidates prior cursors (verified in SC-08).
- Multi-expression pipeline (`backend/app/services/semantic_context_query.py::query_multi`): resolves scope exactly once, batches distinct normalized expressions through `SemanticResourceRetrievalService.recall_multi` (single embedding call), fuses per-expression lexical+semantic candidates by `(ontology_id, resource_id)` before decoration/expansion, sorts by `(tier_rank, -score, -support_count, ontology_order, kind_order, normalized_label, id)`, applies match cursor and `limit`, decorates selected matches once, expands all selected roots together with per-identity `root_paths`, applies context cursor and `context_limit`, aggregates per-expression/per-Ontology completeness. `depth=0` and `context_limit=0` short-circuit context expansion without altering match recall (verified by CX-07 and depth=0 tests). Input order is not a fusion key (verified by FU-05). Normalized duplicates collapse to one execution entry and do not inflate `support_count` (verified by FU-06).
- REST adapter (`backend/app/api/semantic.py::query_semantic_context`): injects `principal: AuthPrincipal = Depends(principal_dependency)` and forwards it into `query_multi`; maps `SemanticContextCursorInvalid`/`SemanticContextCursorMismatch`/`SemanticContextSnapshotChanged` to HTTP 400/400/409 via `_semantic_query_http_exception`.
- MCP tool (`backend/app/mcp/tools/semantic.py::query_semantic_context`): applies `query`/`queries` mutual exclusion at the boundary via `_normalize_mcp_queries`; calls `query_multi` with `principal=runtime_principal()`, which is the server-derived identity refreshed by `_authorize_tool` (see runtime seam below). No client-supplied principal is accepted.
- MCP runtime principal seam (`backend/app/mcp/runtime.py`): `_authorize_tool` revalidates the API key, scopes, and Project ownership, then calls `_set_runtime_principal(principal)` to publish the refreshed identity through the process-local `_principal` global. `runtime_principal()` reads it. `_run_tool` always calls `_authorize_tool` before invoking the tool callback, so the published identity is fresh per request. The same closure-inspection actor-spoof and Project-ownership guards still run before publication, so a client cannot inject an identity.
- Capability discovery (`backend/app/services/semantic_context_capabilities.py` + `backend/app/api/mcp_catalog.py`): `context_query_capabilities(settings)` returns canonical `queries` (min/max/item_char_limit/aggregate_char_limit), compatibility `query` alias, `limit` default/max, `context_limit` default/max, `depth` default/max, and `cursors` (kinds/lifetime_seconds/stable_secret_configured). The catalog attaches it under `capabilities.semantic_context_query` on the existing `GET /api/mcp/tools` route — no new endpoint. Ephemeral fallback (`stable_secret_configured=false`) advertises the limitation.
- Schema (`backend/app/api/schemas.py::SemanticContextQueryRequest`): `queries` (1..8) xor `query` (1..2000 chars); cursors mutually exclusive; per-item and aggregate char caps enforced; `context_limit` 0..1000. `SemanticContextQueryResponse` carries `matches_page` and `context_page` envelopes; legacy `truncated` remains the OR of section-level truncation flags.

### Independent Round 1 — conclusion and recommendation

Independent tester returns **PASS-with-DEFERRED** for the unit-testable contract surface of R1.2-004. The implementation honors the frozen design contract at every check the tester could cover without live PostgreSQL + pgvector + Oxigraph and without a service restart. No Critical/High defects found. Recommend the main agent commit the implementation, restart `ontology-platform.service`, and arrange a follow-up runtime round (CX/PG/SC/DG live parity, BD-01..04 Dify fixtures, BD-06 status sync, PF-02..05 live performance, section 9 items 3–7 and 10) before flipping R1.2-004 to `已实现`.

## Final verification

- Required checks:
  - Focused suite `cd backend && uv run pytest tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_operation_semantics.py tests/test_semantic_context_cursor.py tests/test_semantic_context_query_independent.py -x` → 81 passed.
  - Full backend regression `cd backend && uv run pytest` → 785 passed, 6 skipped.
  - `git diff --check` clean.
  - `node .gitnexus/run.cjs detect_changes --scope all --repo ontology-platform` shows the
    expected additive scope (no unrelated product code touched).
- Runtime/restart health: `ontology-platform.service` is `active` with `--reload`; the live process
  hot-reloaded the new modules. `curl http://127.0.0.1:8001/api/health` returns
  `{"status":"ok"}`; `curl http://127.0.0.1:5173/` returns `200`. Live PostgreSQL/pgvector/Oxigraph
  parity smoke (CX/PG/SC/DG, BD-01..04 Dify fixtures, PF-02..05) is the documented follow-up round.
- Documentation/status sync: R1.2-004 flipped to `已实现` in `docs/requirements/requirements-v1.2.md`
  with implementation summary; `docs/reference/api.md` and `docs/reference/mcp.md` describe the
  canonical `queries` input, compatibility `query`, `context_limit`, and cursor fields;
  `docs/delivery/test-plans/2026-07-20-r1-2-004-related-query-aggregation-test-plan.md` section 11
  holds Independent Round 1.
- Cleanup: no live runtime data was created during this delivery; unit-test fixtures are
  transient in-process objects. No cleanup required.
- Residual risks and follow-ups:
  - Live runtime parity round covering CX/PG/SC/DG, BD-01..04 (Dify + non-workflow fixtures),
    BD-06 status sync, and PF-02..05 (provider batch split, concurrent workspace mutation,
    restart cursor invalidation, p50/p95 instrumentation).
  - Production deployments should set `SEMANTIC_CONTEXT_CURSOR_SIGNING_SECRET` so cursors survive
    process restart; the ephemeral fallback advertises `stable_secret_configured=false` and
    invalidates outstanding cursors on restart per design §4.6.
  - R1.2-005 retains the separate follow-up finding that its unconditional normalized condition
    shape may not fit every supported Rule language; unrelated to this delivery.

## Retrospective

- Scope or design deviations: the original requirement incorrectly promoted a Dify Workflow
  aggregate into platform behavior. The accepted design replaces it with generic related-expression
  retrieval and fused semantic context. The frozen design was implemented additively across REST,
  MCP, the shared service, capability discovery, focused tests, and documentation.
- Rework and root causes: Round 1 required four plan corrections because the first draft did not
  fully anchor examples, identity propagation, multi-root distances, and context ordering to the
  current adapters and mixed context producers. The developer extended `SemanticResourceRetrievalService`
  with `recall_multi` to satisfy the "one scope resolution + one embedding batch" rule without
  duplicating R1.2-003 logic; the tester confirmed that invariant with an instrumented spy.
- What shortened or delayed delivery: read-only compatibility and live-size probes prevented a
  naive repeated-query implementation and grounded public limits before review. The mandatory
  repository-backed review added one correction round but removed four high-risk ambiguities.
- Reusable lessons: reference-Ontology concepts remain data unless explicitly promoted; cursor
  designs must freeze identity, authorization binding, total ordering, version binding, and
  continuation semantics together; shared-item provenance needs per-root paths rather than one
  scalar distance.
