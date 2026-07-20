# R1.2-003 多语言与语义候选召回交付记录

- Requirement source: `docs/requirements/requirements-v1.2.md` R1.2-003
- Status: in-progress — design frozen; product implementation pending
- Started: 2026-07-20T10:41:46+08:00
- Last updated: 2026-07-20T10:57:13+08:00
- Design: `docs/delivery/designs/2026-07-20-r1-2-003-multilingual-semantic-retrieval-design.md`
- Architecture decision: `docs/architecture/decisions/0006-pgvector-semantic-retrieval-projection.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-20-r1-2-003-multilingual-semantic-retrieval-test-plan.md`
- Delivery baseline: `920b5ed7df1e2f3575b6ef5ff0f5fe900c60d432`; pre-existing R1.1-003 and
  `.codex/r11003_*` worktree changes are unrelated and excluded
- Delivery commit: pending; subject will be `Design multilingual semantic retrieval`

## Confirmed contract

- Current behavior: R-006 Context Query performs deterministic lexical matching over scoped RDF and
  current Rule/Operation metadata. English terms such as `support`, `invoice`, and `contract` find
  the Dify synthetic reference resources, while “客服工单”“发票对账”“合同风险审查” return
  `no_match`. The vector projection has only a document builder and `FakeVectorWriter`; the current
  PostgreSQL image has no pgvector extension.
- Target behavior: a shared, scope-safe lexical plus embedding retrieval module returns explicit
  lexical evidence or clearly labeled semantic candidates across Class, Entity, Relation/Property,
  Rule, and Operation resources. It preserves ambiguity, degrades to lexical retrieval when the
  vector path is unavailable, and never turns similarity into an asserted equivalence.
- In scope: pgvector as a rebuildable projection, hybrid-by-default Context/Entity/Class search,
  versioned thresholds, synchronous post-commit index rebuild, REST/MCP parity, migration/backfill
  design, explainable match metadata, and deterministic acceptance coverage.
- Non-goals: Project/Ontology catalog semantic search, arbitrary fact/Evidence/audit indexing,
  query-text persistence, generated translations or aliases, reranking, final answer generation,
  a standalone universal search endpoint, or product-code implementation in this documentation
  delivery.
- Acceptance summary: the three Chinese names recall the intended English workflow candidates;
  mixed-language and identifier variants are replayable; unrelated knowledge remains `no_match`;
  near candidates remain distinguishable; missing/stale/failed indexes are visible and safe.
- Refinement: the user confirmed PostgreSQL + pgvector, Ontology-internal resource scope, no v1
  reranker, hybrid default on Context/Entity/Class searches, synchronous rebuilding with semantic
  truth committed first, metadata-only index text, versioned threshold plus ambiguity margin,
  backward-compatible response extensions, and this complete documentation package.

## Timeline

### 2026-07-20T10:41:46+08:00 — source and current-state audit — main agent

- Context: R1.2-003 is `未实现`; R1.2-002 intentionally excludes multilingual/vector matching and
  leaves Ontology-internal recall to this requirement.
- Action/decision: traced the current Context Query, scope resolver, lexical scorer, REST/MCP
  adapters, entity-search read model, projection job/manifest lifecycle, embedding client, and
  vector projection scaffold. GitNexus reported LOW upstream risk for both
  `SemanticContextQueryService` (4 direct dependents) and `_compose_entity_search` (2 direct
  dependents).
- Evidence: `docs/requirements/requirements-v1.2.md`; `backend/app/services/semantic_context_query.py`;
  `backend/app/services/semantic_vector_projection.py`; read-only GitNexus impact reports.
- Outcome/next step: refine shared retrieval, index lifecycle, response compatibility, and failure
  behavior before writing the design.

### 2026-07-20T10:41:46+08:00 — functional contract frozen — user and main agent

- Context: cross-language recall could rely only on asserted aliases, controlled translation, or a
  shared embedding projection; catalog scope, reranking, freshness, and response compatibility
  materially changed the design.
- Action/decision: selected pgvector hybrid retrieval for Ontology-internal resources; kept
  R1.2-002 catalog discovery deterministic; rejected a v1 reranker; made hybrid the default for
  Context, Entity, and Class search; selected synchronous rebuild after semantic commit with
  `write_applied + index_failed` failure semantics; limited index text to governed semantic
  metadata; preserved `result_status` and added compatible recall/match fields.
- Evidence: user confirmations in the current requirement-refinement session.
- Outcome/next step: record risk probes and freeze numeric/configuration defaults in the design.

### 2026-07-20T10:41:46+08:00 — risk probe 1: real cross-language quality — main agent

- Context: an embedding model is only justified if it recalls the real English resources without
  silently collapsing different semantic targets.
- Action/decision: called the configured `embedding-3` against the live Dify synthetic Ontology.
  Hand-selected comparisons returned the intended Top-1 for support and invoice; contract matched
  both `Assess Contract Risk` and `Quarterly Contract Risk Review`, proving that semantic similarity
  must remain a candidate signal. A 91-resource probe placed relevant support, invoice, and contract
  resources above `0.45`; unrelated weather, salary, and flight queries stayed below `0.40`.
- Evidence: read-only `EmbeddingClient`/Oxigraph probes; no repository or runtime data was modified.
- Outcome/next step: freeze v1 cosine threshold `0.45` and ambiguity margin `0.03`, scoped to the
  exact model/document/projection configuration and guarded by positive/negative corpus tests.

### 2026-07-20T10:41:46+08:00 — risk probe 2: provider batching — main agent

- Context: the provider may reject an Ontology-sized embedding request even when small calls work.
- Action/decision: one 94-input request returned HTTP 400; the same inputs succeeded in batches of
  16.
- Evidence: read-only configured embedding-provider probe; error and successful retry observed in
  the current session.
- Outcome/next step: v1 indexing uses configurable batches with default 16, validates returned
  counts/dimensions, and never assumes provider-wide bulk acceptance.

### 2026-07-20T10:41:46+08:00 — risk probe 3: persistent vector readiness — main agent

- Context: the repository advertises vector projections but may not contain a queryable backend.
- Action/decision: verified the production path still registers `FakeVectorWriter`, PostgreSQL uses
  the stock `postgres:17` image, `pg_available_extensions` contains no `vector`, and backend
  dependencies do not include pgvector.
- Evidence: `docker-compose.yml`, `backend/pyproject.toml`, projection writer registration, and a
  read-only PostgreSQL extension query.
- Outcome/next step: the design includes a pgvector-enabled PostgreSQL image, extension migration,
  durable retrieval documents, atomic manifest promotion, and an explicit existing-data backfill.

### 2026-07-20T10:54:39+08:00 — plan review Round 1 — plan_reviewer and main agent

- Context: the mandatory reviewer checked the requirement, ADR, design, test plan, real Rule CRUD,
  projection state, authorization and pgvector filtered-query assumptions.
- Action/decision: reviewer returned `REVISE` with three High findings. Main agent accepted all:
  (1) Rule commit could precede manifest stale and query validation lacked a Rule signature; DELETE
  204 could not express the documented failure contract; (2) HNSW post-filter under-recall could
  turn an authorized hit into a false complete no-match; (3) ambiguity margin `0.03` lacked one
  score domain.
- Evidence: `backend/app/services/semantic_rule_definition.py`, Rule POST/PATCH/DELETE handlers in
  `backend/app/api/semantic.py`, the reviewed documents, and pgvector's official exact/approximate
  search contract.
- Outcome/next step: revise to transactional Rule+manifest invalidation and query-time rule-set
  signature; keep DELETE 204 with explicit result headers; use exact cosine scan in v1; define
  `effective_score=rank_score/1000` and 29/30/31 point boundaries; then re-review.

### 2026-07-20T10:57:13+08:00 — plan review Round 2 — plan_reviewer and main agent

- Context: Round 2 re-read the requirement, ADR, revised design and shared test plan against the
  same repository paths and all accepted Round 1 findings.
- Action/decision: reviewer returned `PASS` with no remaining evidence-backed Critical/High issue.
  It verified crash-safe Rule signature/invalidation, exact pgvector scope behavior and degraded
  timeout, and the single effective-score/ambiguity domain.
- Evidence: plan_reviewer Round 2 result; revised requirement/design/ADR/test-plan sections.
- Outcome/next step: freeze the documentation design; run final scoped checks and commit only the
  R1.2-003 artifacts. Product implementation and independent test rounds remain pending.

### 2026-07-20T10:57:13+08:00 — documentation verification and handoff freeze — main agent

- Context: this delivery is intentionally limited to the approved requirement/design package and
  must not absorb unrelated R1.1-003 worktree changes or claim product implementation.
- Action/decision: verified all five artifacts exist and are non-empty, checked tracked and new-file
  diffs for whitespace errors, validated their repository-relative artifact paths, and confirmed
  R1.2-003 remains `未实现`. Runtime/product suites and restart were skipped because no backend,
  frontend, migration or runtime file changed.
- Evidence: scoped `git diff --check`, new-file `git diff --no-index --check`, path existence checks,
  scoped `git status`/diff, and plan review Round 2 PASS.
- Outcome/next step: commit only the five R1.2-003 files with subject
  `Design multilingual semantic retrieval`; future implementation starts from this reviewed
  requirement, ADR, design, shared test plan and append-only record.

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | High: Rule commit/stale crash window and DELETE response gap | accepted-high | Rule service commits independently; Rule signature absent from scope | add transactional stale, rule-set signature, mutation headers and crash tests |
| 1 | High: HNSW filtered under-recall | accepted-high | pgvector ANN trades recall; filters may leave too few results | v1 exact cosine scan; ANN deferred to new version and parity gate |
| 1 | High: ambiguity score domain undefined | accepted-high | integer rank score conflicted with decimal margin | define effective_score and 29/30/31 tests |
| 2 | Re-review of all accepted High revisions | resolved-PASS | no remaining evidence-backed Critical/High | documentation design frozen; no further plan revision |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| Documentation 1 | baseline `920b5ed` | Write requirement, ADR, design, test plan, and this record | plan review Round 2 PASS; final checks pending | review-complete |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| Not started | documentation-only delivery | N/A | Product implementation and independent acceptance remain future work | shared test plan |

## Final verification

- Required checks: plan review Round 2 `PASS`; artifact existence/path checks and scoped whitespace/
  diff checks `PASS`; GitNexus staged change detection reports 5 documentation files, risk `low`,
  and zero affected execution processes; final commit pending.
- Runtime/restart health: not required for a documentation-only change; no backend/frontend/runtime
  files will be modified.
- Documentation/status sync: requirement, ADR, design, shared test plan and record are aligned;
  R1.2-003 correctly remains `未实现`.
- Cleanup: no persistent test data created; embedding probes were read-only.
- Residual risks and follow-ups: product implementation, migration rehearsal, real index backfill,
  independent PASS, runtime restart, and R1.2/R-103 status closure remain pending.

## Retrospective

- Scope or design deviations: none at document creation.
- Rework and root causes: pending.
- What shortened or delayed delivery: reusing the existing R-006 scope, match, projection-job, and
  manifest contracts reduced new surface; the current fake vector backend requires explicit infra
  design.
- Reusable lessons: cross-language Top-K quality does not establish semantic equivalence; index
  configuration and negative examples must be versioned together.
