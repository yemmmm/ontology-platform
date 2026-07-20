# R1.2-003 多语言混合语义召回共享测试计划

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-003
- Design: `docs/delivery/designs/2026-07-20-r1-2-003-multilingual-semantic-retrieval-design.md`
- ADR: `docs/architecture/decisions/0006-pgvector-semantic-retrieval-projection.md`
- Delivery record: `docs/delivery/records/2026-07-20-r1-2-003-multilingual-semantic-retrieval-delivery-record.md`
- Contract freeze: 2026-07-20 user-confirmed hybrid/pgvector contract
- Status: completed; Independent Round 8 PASS (prior failures remain below as delivery history)

## 完成门禁

- Alembic 在 pgvector-enabled PostgreSQL 17 上从当前 head 升级成功；既有数据卷演练、fresh install、
  migration precondition failure和 schema/index 检查通过。
- 聚焦 service/repository/API/MCP/read-model/UI 测试和完整 `cd backend && uv run pytest` 通过。
- `cd frontend && npm run build` 与 `cd frontend && npx playwright test` 通过。
- 真实 Oxigraph + PostgreSQL/pgvector + configured embedding provider 上完成 fixed corpus、索引构建、
  查询、同步失败/修复、backfill 和权限验收；mock-only 不足以证明范围和向量行为。
- `systemctl --user restart ontology-platform.service` 后 unit active，`8001/api/health`、`5173/`、
  REST/MCP Context Query、Entity 和 Class 搜索健康。
- requirements、ADR、API、MCP、platform guide、设计实现结果、测试轮次和交付记录同步；R1.2-003
  只有独立 PASS 后才改为 `已实现`。

## 固定评测数据

使用可重复的 Dify synthetic reference Ontology 快照，并另建唯一前缀
`r1-2-003-acceptance-<timestamp>` 的隔离 Ontology。至少包含：

- Workflow Definition：Customer Support Ticket Triage and Reply、Invoice Reconciliation and ERP
  Sync、Quarterly Contract Risk Review；
- 相关但不同类型资源：Run、Log、Published Workflow、Assess Contract Risk Node/Event、Input；
- 中英文 label、带语言 tag label、altLabel、description、SemanticMapping、CamelCase/下划线/连字符
  IRI；
- 两个同名跨 Ontology 资源、两个向量近邻但不同业务含义资源；
- 负例查询：天气预报、员工薪资、航班预订，以及一个确实不存在的稳定 ID；
- 可识别的敏感/禁止索引 literal、Evidence excerpt 和 audit rationale，用于证明不进入索引。

Embedding/model、维度、文档模板、threshold `0.45`、ambiguity margin `0.03` 和 config hash 固定在
测试证据中。Provider 漂移导致 corpus 断言变化时必须新建 projection version，不得放宽同版本
验收。

## 确定性测试矩阵

| 类别 | 场景 | 预期 |
| --- | --- | --- |
| 中文 | 客服工单 | 返回 Customer Support workflow 候选；Run/Log 等近邻保留类型，不静默当作同一资源。 |
| 中文 | 发票对账 | 返回 Invoice Reconciliation workflow 候选，相关 Input/Node 只有达到阈值才作为独立候选。 |
| 中文 | 合同风险审查 | 返回 Quarterly Contract Risk Review 与 Assess Contract Risk 等近邻并标记 ambiguity。 |
| 负例 | 天气/薪资/航班/不存在 ID | current 完整索引下低于 0.45，无词面依据时为完整 `no_match`。 |
| 词面 | exact label/altLabel/Mapping/稳定 ID | `candidate_level=exact`，返回具体依据，优先于仅向量候选。 |
| 变体 | 中英混合、NFKC、casefold、CamelCase、`_`、`-` | 相同 projection/config 下候选、分数和排序可重放。 |
| 阈值 | 0.45 上下边界 | `<0.45` 丢弃，`>=0.45` 保留；浮点比较和返回精度稳定。 |
| 歧义 | Top candidates 分差 29/30/31 rank points | effective_score=rank_score/1000；29/30 为 ambiguous，31 不触发分差歧义。 |
| 歧义 | lexical-only/semantic-only/mixed/多个 exact | 各自按冻结计分域判断；多个 exact 稳定 ID 一律 ambiguous。 |
| 类型 | concept/instance/relation/rule/operation 过滤 | SQL 近邻前施加过滤；不匹配类型不进入 Top-K 或计数。 |
| 范围 | 单/多 Ontology、Project partial scope | 只查 resolver 实际纳入的 Ontology/version，排序遵守调用方范围顺序。 |
| 同名 | 相同 label/IRI 跨 Ontology | 各自稳定 ID、Ontology、版本和依据保留，不跨 Ontology 去重。 |
| 兼容 | 旧请求无 search_mode | 默认 hybrid；保留 result_status 和既有 item 字段，exact 结果稳定。 |
| 诊断 | search_mode=lexical | 不调用 embedding/pgvector，复现词面结果并标记 mode。 |
| REST/MCP | 相同身份、范围、query/filter | 核心候选、顺序、版本、match_status、completeness、index 状态一致。 |
| Entity | entity-search 默认 hybrid | 返回原 row + match/recall；detail 路径和 class filter 不回归。 |
| Class | 中文搜索 Class | concept-filtered 候选只筛选/高亮 topology Class；清空恢复完整图。 |

## 索引构建和版本测试

| 场景 | 预期 |
| --- | --- |
| fresh Ontology build | 16 条分批，数量/1024 维/有限数值校验通过，新 manifest 原子 current。 |
| provider 拒绝大批量 | builder 仍按 16 分批；单批失败 job failed，不提升部分分区。 |
| text hash 未变 | 同 config/version 复用 embedding，不改变最终文档或排序。 |
| model/dimension/template/threshold/margin 变化 | config hash 变化，旧 manifest config_mismatch，不参与 current query。 |
| 构建期间 workspace/source signature 变化 | job conflicted/stale，不提升；下一次重建使用新快照。 |
| Rule current definition/Operation/derived type 变化 | 受影响资源文档更新，旧 definition/类型不冒充 current。 |
| atomic promotion | 查询只看签名匹配的完整 current；旧 current 在新 Rule/RDF signature 下也不可查。 |
| old partition cleanup | 只清理无 manifest/job 引用的明确旧分区；无法证明归属时保留并报告。 |
| existing-data backfill | 可按 Ontology 幂等重试，失败汇总，不输出索引文本；成功项 current。 |

## 降级和失败测试

| 状态/失败 | 预期 |
| --- | --- |
| index missing | 词面继续；recall completeness=degraded、index=missing，不把空结果称为完整无知识。 |
| stale workspace/version | 不查询旧 vector；返回 stale warning，词面使用本次实际 RDF scope。 |
| config mismatch | 不混用不同 model/dimension/template，标记 config_mismatch。 |
| provider timeout/HTTP/invalid payload | 查询降级词面，不回显 URL、payload、密钥或 query；构建 job failed。 |
| pgvector unavailable/query error | 映射稳定 warning；Context/Entity/Class 不因可降级路径全部 5xx。 |
| lexical match + vector failure | 保留 exact/lexical item，match_status 正确但 completeness=degraded。 |
| no lexical + vector failure | result_status=no_match、match_status=no_match、completeness=degraded。 |
| semantic write + successful rebuild | 写入响应 index=current，后续查询使用相同 workspace version。 |
| semantic write + failed rebuild | 权威事实仍可读；响应 write_applied + index_failed/stale，可按 job 重试。 |
| concurrent second write | 第一构建不能覆盖第二版本 manifest；最终只提升当前版本。 |
| Rule commit crash window | Rule 与 manifest stale 已同事务提交；模拟提交后 coordinator 未运行/进程退出，旧 Rule 投影不可查。 |
| Rule POST/PATCH/DELETE | 三条接口都提交事实、原子 stale；POST/PATCH body+headers、DELETE 204 headers 能表达 current/failed 和重建入口。 |

## 安全、隐私和防枚举

- Project-bound read key、组织管理员、外国 Project/Ontology、无认证、无 read scope 分别覆盖；授权
  过滤必须进入 SQL `WHERE`/index scan，不能全库 Top-K 后删响应。
- 外国资源不出现在候选、总数、score、index status、warning、耗时分组或错误详情。
- 检索文档表和 embedding input 检查不含任意 fact literal、Evidence excerpt、audit rationale、
  credential placeholder/secret 或用户 query。
- 应用日志和 delivery evidence 只保存脱敏 query category/hash（若确有必要），默认不保存正文和
  query vector；provider 原始错误经过安全映射。
- Mapping 只在显式 target 指向资源时成为依据，不把相同 external field 跨 Ontology 连接。

## 迁移、发布和真实运行时验收

1. 在 fresh pgvector PostgreSQL 17 和现有同主版本 volume 副本执行 migration；检查 vector/pg_trgm
   extension、column dimension、unique/B-tree/词面 indexes，确认没有 HNSW/IVFFlat，并验证缺
   extension 时 fail fast。
2. 启动未 backfill 的应用，验证 Context/Entity/Class 为 lexical degraded 而不是启动失败。
3. 对隔离 Ontology 运行 backfill，核对 job/manifest/document count、workspace version/config hash，
   重启后 current 仍可查询。
4. 通过公开 REST/MCP 执行三中文、变体、负例、歧义和 scope/auth 场景；保存脱敏断言和状态。
5. 分别通过 modeling batch、governed edit、Rule definition/current pointer 改变资源；验证同步成功。
6. 用可控 provider failure 执行一次写入，证明事实已应用、索引 failed、词面降级；恢复 provider，
   幂等重建并证明 current。
7. Class UI 输入中文选择正确 Class，Entity UI 用中英文查询；刷新/清空/错误/重试行为稳定。
8. 执行完整 backend/frontend/Playwright，重启 systemd 并重复健康和至少一条 REST/MCP hybrid query。

## 性能与资源边界

- Query embedding 每请求最多一次；vector candidate 上限为 `min(200, max(50, limit * 5))`，最终仍受
  Context/read-model limit 约束。
- Build 默认 batch 16；超长 metadata document 截断规则确定且 text hash 基于实际 embedding 文本。
- 用小、中和大 Ontology 记录 query/embed/vector/fusion 分段耗时、索引文档数和构建时间；性能失败
  不得通过降低授权、版本检查或提高阈值掩盖。
- 构造大量外国 Ontology/version 文档包围少量授权候选，比较共享查询与过滤后全量 exact 基线；
  合法候选必须一致，外国文档不得造成 under-recall 或完整 no-match。exact scan 超时必须 degraded。

## 回归和检查命令

产品实现后至少运行：

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run pytest
cd frontend && npm run build
cd frontend && npx playwright test
git diff --check
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

数据库 migration downgrade 只在隔离副本验证，不删除真实索引/扩展。产品测试数据使用唯一前缀和
已记录 ID；只清理能够双重证明归属的数据、jobs、manifests 和文档，无法证明时保留并记录。

## 实现审查检查项

- Shared service/repository 是唯一阈值、config hash、融合、歧义和 index-state 实现；Context、
  Entity、Class adapter 不复制规则。
- pgvector 不是权威语义存储；任何相似结果不写 RDF/Rule/Mapping。
- 同步 index failure 不覆盖语义写成功状态，也不试图不安全删除已提交 RDF。
- manifest promotion 在版本/config 二次检查后原子完成；旧/半写分区永不参与 current query。
- Rule indexed-field signature 在查询时重算；Rule 修改与 manifest stale 同事务，DELETE 204 通过
  headers 保留写入兼容并表达索引结果。
- response 保留 result_status 兼容性，并能区分完整 no-match 与降级 no-match。
- 首版没有 rerank provider、隐藏翻译调用、query cache table 或 Ontology catalog vector search。

## 独立测试轮次

独立 tester 在开发停止写入后的稳定状态追加 Round；不得修改上述合同或删除失败历史。

### Independent Round 1 — 2026-07-20 (FAIL)

- Result: **FAIL**. The retrieval core, migration, provider integration, regression suite and runtime
  health pass, but two High contract defects prevent R1.2-003 acceptance. No product code was changed
  during this round.
- Stable state: developer handoff after `SET LOCAL statement_timeout` was present in
  `PgVectorRetrievalRepository.exact_cosine_candidates`; worktree was stable during execution. Existing
  unrelated dirty files, including `AGENTS.md` and `CLAUDE.md`, were preserved.

#### Passing evidence

- `cd backend && uv run alembic current` returned `0029_pgvector_semantic_retrieval (head)`. The live
  PostgreSQL 17.10 database reported `vector:0.8.5` and `pg_trgm:1.6`; the retrieval embedding column is
  a user-defined `vector`, its DDL is `vector(1024)`, and its indexes are scope B-tree, partition B-tree,
  unique input and `gin_trgm`. The live catalog returned zero HNSW/IVFFlat indexes.
- A real PostgreSQL transaction created a uniquely named, scoped temporary Project/Ontology/Graph Set,
  current manifest and four retrieval documents, then rolled back. The actual repository query returned
  only the in-scope `concept`, excluded a foreign Ontology, wrong kind and stale source signature, returned
  `semantic_candidate`, kept `lexical` complete without an embedding call, mapped provider failure to
  `degraded`, and returned complete `no_match` for a negative vector. `SHOW statement_timeout` was
  `500ms`; document count was `0` before and after rollback.
- A second rollback-only probe used the configured real `embedding-3` provider with real pgvector cosine
  search. It recalled the intended English candidates for all required Chinese names with complete indexes:
  `客服工单` -> `Customer Support Workflow` (0.694), `发票对账` ->
  `Invoice Reconciliation Workflow` (0.661), and `合同风险审查` ->
  `Quarterly Contract Risk Review` (0.761). No test document remained (`0` before/after).
- Metadata-document probe admitted a labelled Class but excluded a fact literal, Evidence excerpt and
  secret marker; the generated record contains no query text or query vector fields. A direct provider
  probe returned one finite 1024-dimensional vector.
- Focused backend checks passed: `cd backend && uv run pytest
  tests/test_semantic_retrieval.py tests/test_semantic_context_query.py
  tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py
  tests/test_semantic_read_model.py tests/test_semantic_class_type_read_models.py
  tests/test_semantic_projection_job.py -q` -> `53 passed`. The required full command
  `cd backend && uv run pytest -q --cache-clear` completed with no `lastfailed` cache (732 collected;
  726 passed/6 skipped). `uv run pytest tests/test_owl_reasoner.py -q` -> `2 passed`; a direct
  `.venv/bin/python` invocation's missing-`rdflib` shebang failure is therefore a non-required-invocation
  environment caveat, not this round's product failure.
- Frontend checks passed: `cd frontend && npm run build` succeeded (only the pre-existing Vite large-chunk
  warning), and `cd frontend && npx playwright test` -> `38 passed`. `git diff --check` passed.
- `systemctl --user restart ontology-platform.service` completed; the unit became active and
  `curl --fail http://127.0.0.1:8001/api/health` returned `{"status":"ok"}`, while
  `curl --fail http://127.0.0.1:5173/` returned the frontend document.

#### Confirmed High defects

1. **Non-Rule semantic writes do not synchronously rebuild the retrieval projection.** R1.2-003 requires
   every current-resource write to commit the authority first, mark/rebuild the affected Ontology index in
   the same request, and report `write_applied` plus the index outcome. The reviewed design explicitly
   includes modeling batches, governed semantic/canonical edits, import/workspace replacement, Operation
   changes and derived-pointer changes. Repository-wide call-site review found `mark_retrieval_stale` and
   `_rebuild_retrieval_for_*` only on Rule Definition POST/PATCH/DELETE
   (`backend/app/services/semantic_rule_definition.py` and `backend/app/api/semantic.py`). The vector
   writer is merely registered with manual projection-job services in REST/MCP. Thus a non-Rule RDF write
   changes the source signature so an old document is rejected/degraded, but does not perform the required
   synchronous rebuild or return the required write/index contract. New coverage only asserts Rule stale
   behaviour.
2. **Entity `hybrid` search does not use the shared fusion and stable-order contract.**
   `SemanticReadModelService._compose_entity_search` retains SPARQL substring rows in their original order,
   appends vector candidates, and for a shared IRI overwrites `existing["match"]` with the semantic match
   (`backend/app/services/semantic_read_model.py:1480-1528`). It neither calls
   `fuse_context_candidates` nor computes lexical exact evidence, stable fusion ordering, or a post-fusion
   limit. An Entity with an exact lexical label plus a vector result can therefore be reported as only
   `semantic_candidate`, and Entity ordering can diverge from Context Query. This violates the requirement
   that Context, Entity and Class use the same candidate basis, thresholds and stable ordering.

#### Blocked or intentionally unexecuted runtime cases

- The local service has no configured bootstrap or MCP API key. Unauthenticated Context and read-model
  calls correctly returned `401`, and `python -m app.mcp.server` failed closed with
  `ONTOLOGY_MCP_API_KEY is required`. Consequently authenticated live REST/MCP parity, Rule response-header
  checks and the public three-Chinese-name trace could not be run without creating credentials.
- The live database has zero retrieval documents and existing Ontologies were not backfilled. To preserve
  permanent business data, this round did not create a persistent index or execute governed/modeling writes.
  Existing-data backfill, authenticated public queries, write-success/failure/retry, concurrent-write and
  Rule crash-window cases must be re-run after the two defects are repaired and an authorized isolated
  fixture is available.

#### Residual risk and repair gate

Repair must route every in-scope semantic write through one coordinator that preserves fact-first semantics,
atomically invalidates the correct manifest, synchronously rebuilds and reports the per-Ontology outcome.
Entity search must reuse the Context fusion/scoring/sorting helper (or an equivalent single shared helper)
without discarding lexical evidence. A new independent round must then verify all authenticated REST/MCP
paths against a backfilled isolated Ontology before this requirement can pass.

### Independent Round 2 — 2026-07-20 (FAIL)

- Result: **FAIL**. Both High defects from Round 1 were repaired and their affected regressions pass, but
  independent acceptance review found two different High retrieval-contract defects. No product code or
  delivery record was changed during this round.
- Stable state: repair handoff with `SemanticRetrievalCoordinator` in the shared retrieval module,
  coordinator calls from governed RDF/canonical/modeling write paths, and Entity post-fusion sorting. The
  prior Round 1 evidence remains valid for migration, pgvector, real-provider cross-language recall,
  privacy and authenticated-runtime limitations.

#### Round 1 repair verification

- `SemanticService.apply_edit` commits authoritative RDF/audit state, then calls
  `SemanticRetrievalCoordinator.rebuild_affected` with its affected graph IRIs. The canonical writer invokes
  the same coordinator only after `commit=True`, and `ModelingBatchService._execute` commits the final
  attempt before rebuilding by Ontology ID. The coordinator persists stale manifests before it starts a
  disposable projection job and returns stable `current|stale|failed` data without rolling back the
  authoritative write.
- Entity search now constructs lexical candidates, converts vector rows to the same shape, calls
  `fuse_context_candidates`, applies deterministic evidence-first sorting, and applies the limit after
  fusion. Targeted E2E assertions confirm a lexical/vector duplicate remains `exact`/`mixed`, preserves
  the lexical row's authoritative fields, and is sorted/truncated after fusion.
- Affected regression command passed: `cd backend && uv run pytest
  tests/test_semantic_retrieval.py tests/test_semantic_service.py
  tests/test_semantic_migration_service.py tests/test_modeling_batches_service.py
  tests/test_semantic_stage4_e2e.py tests/test_semantic_context_query.py
  tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py
  tests/test_semantic_read_model.py tests/test_semantic_class_type_read_models.py -q` -> `142 passed`.
- Full required backend suite `cd backend && uv run pytest -q --cache-clear` passed (731 passed, 6 skipped);
  `git diff --check` passed. `cd frontend && npm run build` passed with only the existing Vite large-chunk
  warning; `cd frontend && npx playwright test` -> `38 passed`. After
  `systemctl --user restart ontology-platform.service`, the unit was active and both
  `http://127.0.0.1:8001/api/health` and `http://127.0.0.1:5173/` passed.

#### Confirmed High defects

1. **Context Query does not prioritize exact evidence over a higher-scoring semantic-only candidate.**
   `fuse_context_candidates` correctly labels exact evidence, but
   `backend/app/services/semantic_context_query.py:_sort_key` sorts only numeric `match.score` before
   Ontology/kind/label/ID. Exact alias and identifier lexical matches are deliberately scored `900` and
   `600`, whereas a semantic-only candidate may score up to `1000`. A direct deterministic probe fused an
   `exact_alias` candidate at `900` with a semantic-only candidate at `950`; Context sorting returned the
   semantic candidate first. This violates the required rule that exact label/altLabel/Mapping/stable-ID
   evidence always ranks before a merely similar candidate. Existing fusion tests check one duplicate but
   not the required cross-resource ranking invariant.
2. **Mapping terms cannot produce an exact Mapping result or return Mapping evidence.** Repository review
   found `exact_mapping` only in the constant used to interpret reasons. The projection builds and SQL reads
   `mapping_evidence`, but no Context/Entity lexical candidate producer emits `exact_mapping`, and
   `_semantic_candidate` discards the selected mapping evidence. A mapping term can therefore influence only
   an opaque semantic candidate, not the required explicit Mapping match with evidence and exact priority.
   No regression covers this contract.

#### Remaining unexecuted cases and residual risk

- The local service still has no bootstrap/MCP key and its permanent retrieval document count remains zero;
  authenticated REST/MCP parity, public traces over backfilled existing data, write header checks and true
  write/rebuild integration against an authorized isolated Ontology remain blocked without changing
  permanent data.
- After repairing the two defects above, the next round must add boundary tests for exact alias/identifier/
  Mapping versus higher vector scores, expose Mapping evidence in REST/MCP and Entity/Class where relevant,
  then repeat the authenticated/backfilled runtime matrix. Until then a consumer can be led to a less
  trustworthy semantic candidate and cannot inspect a Mapping-backed match, so R1.2-003 cannot pass.

### Independent Round 3 — 2026-07-20 (FAIL)

- Result: **FAIL**. The two High defects recorded in Round 2 are repaired and independently pass their
  Context, Entity, REST/MCP-contract and regression gates. A further High Mapping-contract omission remains:
  the implementation does not make a Mapping `target_type` an exact lexical Mapping term, although the
  approved design includes it in the governed Mapping term set. No product code or delivery record was
  changed during this round.
- Stable state: developer handoff containing exact-before-score Context ordering and the shared scoped
  `governed_mapping_lexical_candidates` producer used by Context and Entity. Existing Round 1 evidence for
  migration, pgvector, real-provider multilingual recall, metadata privacy, and the authorized-runtime
  limitation remains applicable.

#### Round 2 repair verification

- `SemanticContextQueryService` now fuses governed Mapping lexical rows before vector rows and `_sort_key`
  puts `candidate_level=exact` before rank score. The independent cases
  `test_exact_alias_precedes_higher_scoring_semantic_candidate` and
  `test_exact_mapping_evidence_precedes_higher_scoring_semantic_candidate` pass: an exact `0.90` alias or
  Mapping result precedes a distinct semantic-only `0.95` candidate.
- Context and Entity both call `governed_mapping_lexical_candidates`; its SQL predicate bounds active Mapping
  rows to the resolved Ontology IDs, and fusion remains keyed by `(ontology_id, iri)`. The independent
  cross-Ontology test passes with each target retaining only its own Mapping evidence, while the Entity E2E
  test returns an `exact`/`mapping` instance before a `0.95` semantic candidate and exposes its safe
  `mapping_evidence` payload.
- Focused public-contract and repair regressions passed: `cd backend && uv run pytest -q
  tests/test_semantic_context_query.py::test_exact_mapping_evidence_precedes_higher_scoring_semantic_candidate
  tests/test_semantic_context_query.py::test_exact_alias_precedes_higher_scoring_semantic_candidate
  tests/test_semantic_context_query.py::test_mapping_evidence_stays_with_its_same_ontology_target
  tests/test_semantic_stage4_e2e.py::test_entity_search_returns_exact_governed_mapping_evidence
  tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py
  tests/test_semantic_retrieval.py` -> `25 passed`.
- Full backend gate passed: `cd backend && uv run pytest -q --cache-clear` -> `735 passed, 6 skipped`.
  `cd frontend && npm run build` passed with only the existing Vite large-chunk warning, and
  `cd frontend && npx playwright test` -> `38 passed`. After restarting
  `ontology-platform.service`, it became active; both `/api/health` and the frontend root returned success,
  and `git diff --check` passed. The first post-restart curl occurred during startup and returned connection
  refused; the retry and final probes passed after the service reported ready.

#### Confirmed High defect

1. **Mapping `target_type` is indexed but cannot be an exact Mapping lexical match.** The approved design
   requires the Mapping term set to include external-field local name, join key, **target type**, and Mapping
   ID. The deterministic document builder includes all four, but
   `governed_mapping_lexical_candidates` compares only `mapping_id`, `mapping_external_field`, and
   `mapping_join_key`; it omits `evidence["target_type"]`. An isolated direct probe over one active,
   in-scope `class` Mapping returned `exact_mapping` for `customer_id` and `mapping-customer`, but `[]` for
   `class`. Therefore callers cannot receive the required explicit exact evidence when the target-type
   Mapping term is the query, even though it is in the indexed document text. There is no regression for this
   required Mapping field. This is a High contract defect because a governed explicit Mapping term degrades
   to an absent/semantic-only answer rather than deterministic exact evidence.

#### Remaining unexecuted cases and residual risk

- A repair must add `target_type` to the governed exact Mapping candidate fields, preserve evidence and scope
  isolation, and add Context/Entity boundary tests with a higher-scoring semantic candidate. Repeat this
  independent round after that repair.
- The service still lacks a bootstrap/MCP credential. The live public Context probe correctly returned
  `401 invalid_authentication`; authenticated REST/MCP parity, response-header checks and public Chinese-name
  trace remain blocked without authorized credentials.
- Persistent retrieval document count remains zero, so existing-data backfill, authenticated live Mapping
  traces, write/rebuild/retry integration, concurrent-write and crash-window tests remain intentionally
  unexecuted to avoid changing permanent business data. Until the target-type repair and that authorized,
  backfilled runtime matrix pass, R1.2-003 cannot be accepted.

### Independent Round 4 — 2026-07-20 (BLOCKED)

- Result: **BLOCKED**. Every previously confirmed High defect now passes independent source, direct-probe and
  regression verification; no new product defect was found. R1.2-003 cannot yet receive a requirement-level
  PASS because its required authenticated public-runtime and existing-data-backfill gates remain unavailable
  in this environment. No product code or delivery record was changed during this round.

#### Prior defects independently reverified as repaired

- The Round 3 Mapping target-type gap is closed. The active, Ontology-bound exact Mapping allow-list now
  emits `mapping_target_type` from safe `target_type` evidence. An isolated direct probe over one scoped
  `class` Mapping returned `exact_mapping` with `matched_fields=["mapping_target_type"]` for query `class`,
  and retained the expected safe Mapping evidence. The same probe still returned exact evidence for external
  field and Mapping ID; no raw join values or unrelated Ontology data were exposed.
- Context keeps the exact-before-score boundary: exact alias and Mapping candidates at `0.90` precede a
  separate semantic-only candidate at `0.95`. Mapping candidates remain limited to active Mapping rows in
  resolver-provided Ontology scope and fuse by `(ontology_id, iri)`, so cross-Ontology evidence does not join
  onto the wrong resource.
- Entity uses the same producer/fusion/order path. Its target-type `entity` case returns an exact Mapping
  candidate with `mapping_target_type` evidence before a higher-score semantic candidate. Round 1 fact-first
  write/rebuild outcomes and post-fusion Entity ordering remain covered by the affected service tests.

#### Passing evidence

- Broader focused repair/public-contract suite passed: `cd backend && uv run pytest -q
  tests/test_semantic_context_query.py::test_exact_mapping_evidence_precedes_higher_scoring_semantic_candidate
  tests/test_semantic_context_query.py::test_exact_alias_precedes_higher_scoring_semantic_candidate
  tests/test_semantic_context_query.py::test_mapping_evidence_stays_with_its_same_ontology_target
  tests/test_semantic_stage4_e2e.py::test_entity_search_returns_exact_governed_mapping_evidence
  tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py
  tests/test_semantic_retrieval.py tests/test_semantic_service.py
  tests/test_semantic_migration_service.py tests/test_modeling_batches_service.py` -> `113 passed`.
- Full backend gate passed: `cd backend && uv run pytest -q --cache-clear` -> `735 passed, 6 skipped`.
  `cd frontend && npm run build` passed with only the existing Vite large-chunk warning and
  `cd frontend && npx playwright test` -> `38 passed`.
- `systemctl --user restart ontology-platform.service` completed. The first 15-second curl window occurred
  while `start-local.sh` was synchronizing dependencies, applying migrations and rebuilding the frontend; the
  unit journal then reported backend/frontend ready. Final `/api/health` and frontend-root probes passed, the
  unit is active, and `git diff --check` passed.

#### Remaining blocked acceptance gates and residual risk

- No bootstrap/MCP credential is configured. Authenticated live REST/MCP parity, response-header checks and
  the public Chinese-name trace cannot be executed without authorized credentials; unauthenticated calls are
  correctly fail-closed.
- The persistent retrieval document count remains zero. Existing-data backfill and its live multilingual
  recall, plus authorized isolated write/rebuild/retry, concurrent-write and crash-window probes, remain
  intentionally unexecuted to avoid modifying permanent business data.
- There is no remaining reproduced code-level defect in the repaired scope. The residual risk is limited to
  the blocked deployment/data gates above; completion requires an authorized isolated fixture, explicit
  backfill, and a final independent public-runtime pass.

### Independent Round 5 — 2026-07-20 (FAIL)

- Result: **FAIL**. An authorized, isolated live fixture removed the Round 4 authentication and existing-data
  restrictions and reproduced a High runtime defect at the first public retrieval gate. An explicit persistent
  vector backfill reported `succeeded`, generated five documents, and promoted a `current` manifest, but an
  authorized Chinese Context query against that same fixture returned `config_mismatch`, `degraded`, and
  `no_match` with no primary results. No product code or delivery record was changed during this round.

#### Fixture, public REST evidence, and cleanup

- The harness created a unique temporary organization-admin API key through the application `create_api_key`
  workflow (the key value was never printed), then used authorized REST calls to create an isolated Project and
  Ontology and load a minimal TriG dataset. The fixture included a Chinese-labeled
  `Customer Support Workflow` resource and its governed semantic retrieval inputs.
- The explicit vector job used projection version `semantic-retrieval-v1`, embedding model `embedding-3`,
  dimensions `1024`, and threshold `0.45`. It completed with `status=succeeded`, `document_count=5`; the
  resulting retrieval manifest was `current` with `document_count=5`.
- The authorized Context request that should have returned the exact `Customer Support Workflow` label instead
  returned HTTP `200` with `result.status=no_match`, `completeness=degraded`,
  `match_status=no_match`, `index_statuses=["config_mismatch"]`, no primary candidates, and warnings
  `derived_result_missing` (twice) plus `vector_index_config_mismatch`.
- The harness stopped at this first observable public failure; authorized Entity/Class, MCP-parity, and
  non-Rule write/rebuild success/failure/degraded/recovery probes were therefore not run. This is a defect
  stop, not an environment block.
- Cleanup was completed in the same `finally` path: the exact fixture RDF named graphs were dropped, the
  temporary Project was removed through its public API, and only fixture-owned retrieval rows, graph-set,
  Ontology/Project state, and temporary API key were revoked/deleted. Final residual counts were zero for RDF
  graphs, documents, edits, graph sets, jobs, keys, manifests, ontologies, and projects.

#### Confirmed High defect and root-cause evidence

- **High — successful current vector backfill is not queryable by its own public Context reader.** R1.2-003
  requires persistent vector retrieval to make the promoted current projection available to multilingual
  semantic retrieval. Here, the writer reported five documents and a current manifest while the public reader
  considered the exact same projection configuration mismatched and returned no candidates; this blocks the
  required persistent-backfill acceptance path.
- In `PgVectorRetrievalRepository.index_status`, `config_mismatch` is returned when a current manifest exists
  but no retrieval document matches the reader identity predicates for graph set, Ontology, workspace version,
  source/rule signatures, projection version, embedding-config hash, and active job. The live evidence proves
  that at least one writer/reader identity value differs despite the visible projection and embedding settings
  matching. The exact differing predicate was not retained after safe fixture cleanup and remains for the
  implementation repair to identify; likely candidates must be audited from the writer metadata through the
  reader's document lookup, rather than weakening the reader's isolation checks.

#### Required re-test after repair

- Re-run an isolated authorized fixture end to end: persistent Chinese-name Context plus Entity/Class retrieval,
  MCP parity, and the non-Rule write/rebuild success, failure, degraded, recovery, and retry matrix. Confirm the
  promoted manifest's document identity values are precisely those used by the public reader and that cleanup
  again leaves no fixture-owned state.

### Independent Round 6 — 2026-07-20 (FAIL)

- Result: **FAIL**. The Round 5 workspace-version reader/writer repair is verified for an initial persistent
  backfill, including authorized REST/MCP Context parity. Three separate fresh, uniquely prefixed fixtures then
  exposed three remaining High acceptance defects: Chinese exact labels are downgraded to semantic candidates,
  the public Entity/Class adapters do not expose the required hybrid retrieval contract, and a successful
  non-Rule semantic write cannot rebuild or recover its vector projection. No product code or delivery record
  was changed during this round.

#### Passing persistent-backfill and REST/MCP evidence

- In the first authorized fixture, dataset load returned HTTP `200`; the explicit ontology retrieval rebuild
  returned `current`; and the Chinese Context request returned `matched`, `completeness=complete`,
  `index_statuses=["current"]`, and one primary result for the expected scoped Class. The temporary Project was
  deleted with HTTP `204`, all four fixture RDF graphs were absent afterwards, and Project, Ontology, document,
  and key residual counts were zero.
- In the expanded fixture, the explicit persistent rebuild wrote three documents and promoted a `current`
  manifest with an active job. Authorized REST and a stdio MCP server authenticated with a temporary
  Project-admin key both returned the same expected Chinese Class, `matched`, `complete`, and
  `index_statuses=["current"]`. No plaintext temporary key was printed.
- A controlled fixture-local embedding failure through the official projection-job service produced a persisted
  failed job; public Context safely retained exact lexical evidence while returning `completeness=degraded` and
  `index_statuses=["stale"]`. This confirms the failure-to-degraded reader path itself.

#### Confirmed High defects

- **High — an exact Chinese `rdfs:label` is returned as a semantic candidate.** The fixture Class had the
  exact Chinese label `客户支持工作流`. REST and MCP both found that exact Class, but both returned
  `match_status=candidate` and only `candidate_level=semantic_candidate`, `method=semantic`,
  `semantic_similarity=0.637`, with no lexical score, matched field, or `exact_label` reason. The frozen
  contract requires exact label evidence to remain in the `exact` layer ahead of candidate scoring; a successful
  vector hit must not discard that deterministic evidence.
- **High — public Entity/Class routes do not deliver the shared hybrid adapter contract.** Authorized
  `GET /api/ontologies/{ontology_id}/semantic-read-models/entities?q=客户支持工作流实例` returned HTTP `200`
  but zero items, no expected Entity, and no `recall` object despite a current three-document projection. The
  Class request with `q=客户支持工作流` returned the Class only as an unfiltered topology row (two items) and
  likewise omitted `recall` and any match metadata. The product route constructs `SemanticReadModelService`
  without a retrieval service, while the generic Class path has no query adapter; these responses therefore do
  not expose the required shared service, index status, or exact/candidate ordering.
- **High — non-Rule write applies its RDF fact but leaves vector retrieval stale and unrecoverable.** An
  authorized Turtle edit against the fixture asserted Ontology graph returned HTTP `200` and `applied=true`,
  but its `retrieval_indexes=[{"status":"failed","write_applied":true}]`. The newly written exact Chinese
  Class remained lexically visible, but Context correctly became `degraded` with `index_statuses=["stale"]`.
  The admin-only `POST /api/semantic/ontologies/{ontology_id}/retrieval:rebuild` retry also returned `failed`,
  so the required recovery path cannot restore a current projection.
- **High — rebuild document identity collides across workspace versions and masks failure state.** A focused
  replay began with two persisted documents and a `current` manifest. The non-Rule edit changed
  `ModelingWorkspaceVersionService.version_for(...)`, while the graph-set source signature stayed unchanged.
  `semantic_retrieval._document_record` derives each document primary key only from
  `graph_set_id|resource_iri|resource_kind|projection_version`, excluding workspace version, source signature,
  and job/partition. Rebuilding unchanged resources into the new workspace therefore reuses existing primary
  keys when `write_documents(... add_all/flush)` writes the new partition. Runtime evidence showed the new job
  left `running`, with `document_count=0`, an empty stored error, and a stale manifest: the flush failure is not
  durably transitioned to the required `failed` job state. This is also why the public retry remains failed.

#### Cleanup and required re-test

- Each fixture used a unique temporary organization-admin key; MCP used a separate temporary Project-admin key.
  Every `finally` path dropped only its known workspace RDF graphs, deleted the fixture Project, revoked/deleted
  the exact temporary keys, and removed fixture-only documents, jobs, manifests, graph state/registry/revisions,
  and edit audit. The full fixture's final residual counts were zero for RDF graphs, Project, Ontology,
  documents, jobs, manifests, both keys, and edit audits.
- After repair, repeat the isolated end-to-end matrix: exact Chinese Context evidence plus REST/MCP parity,
  Entity and Class hybrid responses (including `recall`), non-Rule write `applied/current`, controlled provider
  failure `applied/degraded`, and admin retry recovery to `current`. Verify each replacement partition can keep
  historical rows without primary-key collision and that a rebuild exception persistently marks its job failed.

### Independent Round 7 — 2026-07-20 (FAIL)

- Result: **FAIL**. The Round 6 public Entity/Class adapter and non-Rule replacement-build repairs work in a
  fresh live fixture, as do persisted provider-failure and recovery states. However, the required multilingual
  exact-evidence contract is still not met: the exact asserted Chinese label for a resource with both English
  and Chinese labels remains a semantic candidate in public REST and MCP Context, and is not `exact_label` in
  Entity hybrid output. No product code or delivery record was changed during this round.

#### Runtime and migration preflight

- `/api/health` returned `{"status":"ok"}` and `cd backend && uv run alembic current` reported
  `0030_retrieval_partition_id (head)` before the live probe.
- Every fixture used a newly generated organization-admin key; the REST/MCP fixture also used a separate
  temporary Project-admin key. No key value was printed.

#### Repaired paths independently verified

- The initial explicit backfill wrote three documents, promoted a `current` manifest with an active job, and
  returned `status=current`.
- `GET /api/ontologies/{ontology_id}/semantic-read-models/classes?q=客户支持工作流&search_mode=hybrid`
  returned only the expected Class, with `recall` present, `completeness=complete`,
  `index_statuses=["current"]`, and exact-label evidence. Entity hybrid now also returned the expected Entity
  with `recall` present, `complete`, and `current`; its remaining exact-evidence defect is recorded below.
- An authorized non-Rule Turtle edit returned `applied=true`,
  `retrieval_indexes=[{"status":"current","write_applied":true}]`. The current post-write Context query
  was `matched`, `exact`, `complete`, and `current`; an explicit admin rebuild retry also returned `current`.
  Retrieval documents increased from three to seven without a primary-key collision, confirming that the
  replacement-partition identity repair handles unchanged documents plus the new Class.
- A separate fixture forced an embedding call by using a fixture-only alternate document-template config hash.
  After the current manifest was marked stale, the official projection-job service persisted
  `job_status=failed` with a non-empty error. Public Context returned `matched` lexical evidence with
  `completeness=degraded` and `index_statuses=["stale"]`; the public admin rebuild then returned `current`, and
  Context returned `complete` with `index_statuses=["current"]`.

#### Remaining High defect

- **High — multilingual asserted labels are still not all promoted into exact evidence.** A scoped Class carried
  both `rdfs:label "Customer Support Workflow"@en` and the exact asserted Chinese
  `rdfs:label "客户支持工作流"@zh`. Authorized REST Context and stdio MCP Context both returned the expected
  resource and agreed on `matched`, `complete`, and `index_statuses=["current"]`, but each returned
  `match_status=candidate`, `candidate_level=semantic_candidate`, `method=semantic`, and
  `semantic_similarity=0.637`, with no lexical field or `exact_label` reason. The public Entity hybrid query
  similarly returned the expected Chinese-labeled Entity and a current recall envelope, but did not mark it as
  `exact_label`. Class hybrid is the contrasting repaired path: it did promote the expected exact label.
- R1.2-003 requires all label/alias evidence to retain the exact layer ahead of semantic ranking. The remaining
  defect appears to be the Context/Entity handling of multiple language labels for one IRI, not index health or
  REST/MCP scope parity. It prevents acceptance of the multilingual exact-match contract.

#### Cleanup and required re-test

- Both Round 7 fixture `finally` paths deleted their Projects with HTTP `204`, dropped only their four known RDF
  graphs, revoked/deleted temporary keys, and removed fixture-only documents, jobs, manifests, graph state,
  registry/revisions, and edit audits. Final residual counts were zero for RDF graphs, Projects, Ontologies,
  documents, jobs, manifests, temporary keys, and edit audits.
- After correcting multi-label exact promotion, repeat the isolated bilingual Class and Entity checks through
  REST and stdio MCP. Require `match_status=exact`, `candidate_level=exact`, and `exact_label` evidence for the
  Chinese query while retaining the verified current/degraded/recovery matrix.

### Independent Round 8 — 2026-07-20 (PASS)

- Result: **PASS**. A fresh authorized fixture verified the Round 7 bilingual label repair and re-ran every
  prior High acceptance path: persistent current rebuild, exact Chinese REST/MCP Context, Entity/Class hybrid
  adapters, non-Rule write/retry, persisted provider failure degradation, and public recovery. No product code
  or delivery record was changed during this round.

#### Runtime, migration, and exact-evidence evidence

- `/api/health` returned `{"status":"ok"}` and `cd backend && uv run alembic current` reported
  `0031_retrieval_label_evidence (head)` before fixture creation.
- The explicit initial rebuild wrote three documents, returned `current`, and promoted one current manifest with
  an active job. The bilingual Class carried English plus exact Chinese `rdfs:label` values.
- Authorized REST Context and stdio MCP Context both returned that Class for `客户支持工作流` with
  `result_status=matched`, `match_status=exact`, `completeness=complete`,
  `index_statuses=["current"]`, and exact-label evidence (`method=mixed`). MCP returned `ok=true`; no temporary
  key value was printed.
- Authorized Entity and Class hybrid public routes both returned their expected Chinese-labeled resource with
  `exact_label`, a present `recall` envelope, `completeness=complete`, and
  `recall.index_statuses=["current"]`.

#### Write, failure, and recovery evidence

- An authorized non-Rule Turtle edit returned `applied=true` and
  `retrieval_indexes=[{"status":"current","write_applied":true}]`. The new Chinese Class was immediately
  `matched/exact/complete/current`; the explicit admin retrieval retry again returned `current` with the same
  public Context result.
- After marking only the fixture manifest stale, a fixture-only alternate document-template config forced the
  controlled embedding provider failure. The official projection job persisted `status=failed` with a non-empty
  error. Context retained exact lexical evidence while returning `degraded` and `index_statuses=["stale"]`.
  The authorized public rebuild recovered to `current`; Context then returned `complete` and
  `index_statuses=["current"]`.

#### Cleanup

- The `finally` path deleted the fixture Project with HTTP `204`, dropped only its four known RDF graphs,
  revoked/deleted the exact organization-admin and Project-admin keys, and deleted fixture-only retrieval
  documents, jobs, manifests, graph registry/state/revisions, and edit audit. Residual counts were zero for RDF
  graphs, Projects, Ontologies, documents, jobs, manifests, both keys, and edit audits.
