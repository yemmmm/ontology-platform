# R1.2-004 相关查询表达式联合语义上下文聚合交付记录

- Requirement source: `docs/requirements/requirements-v1.2.md` R1.2-004
- Status: design-delivered; implementation-pending
- Started: 2026-07-20T17:27:33+08:00
- Last updated: 2026-07-20T21:00:26+08:00
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

- Context: the mandatory reviewer returned `REVISE` with four evidence-backed High findings.
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

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| Not run | no implementation handoff | NOT RUN | all product/runtime cases deferred by explicit scope | shared test plan section 11 |

## Final verification

- Required checks: `git diff --check` passed; required artifact paths exist; requirement/design/test
  plan/record status search passed; mandatory plan review passed after two rounds. GitNexus
  `detect_changes(scope=all)` reported LOW risk and no affected execution process for tracked
  documentation changes.
- Runtime/restart health: intentionally not run because no backend/frontend/runtime code changed and
  implementation is explicitly deferred.
- Documentation/status sync: `AGENTS.md` records the platform/reference-Ontology boundary;
  R1.2-004 is rewritten and remains `未实现`; design and shared test plan are reviewed and linked.
- Cleanup: no test or runtime data was created; no cleanup required.
- Residual risks and follow-ups: future implementation must perform fresh symbol impact analysis,
  pass the shared product test plan with PostgreSQL/pgvector/Oxigraph, run independent testing,
  restart/verify the service, and only then change R1.2-004 to `已实现`. R1.2-005 retains the separate
  follow-up finding that its unconditional normalized condition shape may not fit every supported
  Rule language.

## Retrospective

- Scope or design deviations: the original requirement incorrectly promoted a Dify Workflow
  aggregate into platform behavior. The accepted design replaces it with generic related-expression
  retrieval and fused semantic context. No product implementation occurred by explicit user scope.
- Rework and root causes: Round 1 required four plan corrections because the first draft did not
  fully anchor examples, identity propagation, multi-root distances, and context ordering to the
  current adapters and mixed context producers.
- What shortened or delayed delivery: read-only compatibility and live-size probes prevented a
  naive repeated-query implementation and grounded public limits before review. The mandatory
  repository-backed review added one correction round but removed four high-risk ambiguities.
- Reusable lessons: reference-Ontology concepts remain data unless explicitly promoted; cursor
  designs must freeze identity, authorization binding, total ordering, version binding, and
  continuation semantics together; shared-item provenance needs per-root paths rather than one
  scalar distance.
