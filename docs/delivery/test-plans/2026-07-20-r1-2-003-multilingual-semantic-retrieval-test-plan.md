# R1.2-003 多语言混合语义召回共享测试计划

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-003
- Design: `docs/delivery/designs/2026-07-20-r1-2-003-multilingual-semantic-retrieval-design.md`
- ADR: `docs/architecture/decisions/0006-pgvector-semantic-retrieval-projection.md`
- Delivery record: `docs/delivery/records/2026-07-20-r1-2-003-multilingual-semantic-retrieval-delivery-record.md`
- Contract freeze: 2026-07-20 user-confirmed hybrid/pgvector contract
- Status: planned; independent rounds append below and never replace prior failures

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

### Independent Round 1 — pending

- Result: pending product implementation.
- Stable state: pending.
- Evidence: pending.
- Defects/unexecuted cases: all product/runtime cases remain unexecuted in this documentation-only
  delivery.
