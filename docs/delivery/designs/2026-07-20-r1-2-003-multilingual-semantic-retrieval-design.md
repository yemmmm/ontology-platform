# R1.2-003 多语言混合语义召回设计

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-003
- Architecture decision: `docs/architecture/decisions/0006-pgvector-semantic-retrieval-projection.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-20-r1-2-003-multilingual-semantic-retrieval-test-plan.md`
- Delivery record: `docs/delivery/records/2026-07-20-r1-2-003-multilingual-semantic-retrieval-delivery-record.md`
- Contract frozen: 2026-07-20 user-confirmed decisions
- Status: implemented; independent Round 8 PASS after migrations `0029`–`0031`

## 实现结果

- PostgreSQL/pgvector 持久化投影、预过滤 exact cosine、版本化文档身份和安全降级已交付；旧多标签
  投影在 `0031` 后显式 stale，需重建后才作为 complete 检索参与查询。
- Context、MCP、Entity 与 Class 复用候选融合、精确证据、稳定排序和 `recall` 合同；非 Rule 写入
  同步重建或以 `failed|stale` 明确降级，不回滚已提交权威事实。
- 交付证据、失败/修复轮次和最终独立验收见共享测试计划与交付记录。

## 目标

让消费 Agent 在已经明确授权 Project/Ontology 范围后，可以用中文、英文、混合语言或业务/API
命名变体定位本体内部资源。平台返回可验证的词面依据或明确标注的语义候选，保留歧义并在索引
不可用时安全降级，不要求调用方先知道英文标签、内部 Graph Set 或 predicate IRI。

同一检索能力服务 R-006 Context Query、Entity 搜索和 Class 搜索。RDF Dataset 与活动 Rule
Definition 继续是权威语义数据，pgvector 只是可重建投影。

## 非目标

- 不改变 R1.2-002 Project/Ontology 目录的确定性发现、授权和防枚举合同。
- 不建立通用问答、翻译、别名生成、Ontology 自动合并或新的语义事实写入能力。
- 不索引任意事实 literal、Evidence 原文、审计/Agent rationale、凭证或查询正文。
- 不新增独立万能搜索 REST/MCP，不引入 rerank，不选择历史/release 版本。
- 不替代 R1.2-004 聚合读模型、R1.2-005 规则解释或 R1.2-006 有效分类视图。

## 当前状态与设计依据

- `SemanticContextQueryService` 已统一 REST/MCP 的范围解析、词项规范化、候选排序、邻域展开、
  lineage/Evidence 装饰和 `matched|no_match` 响应。
- 当前词面模板读取 label、skos:altLabel、description、IRI/predicate 和 literal 值；Rule/Operation
  候选分别来自 PostgreSQL/RDF。英文 `support|invoice|contract` 可召回真实 Dify synthetic 资源，
  三个中文名称均为 `no_match`。
- `SemanticProjectionJobService` 已有 job、manifest、source signature、派生 pointer 和 stale
  reconcile 合同，但 Vector writer 仍为 fake，PostgreSQL 也没有 vector extension。
- 当前 Entity Search 是 SPARQL read model；Class 页面先读取完整 topology，再在前端做 substring
  高亮。两者需要复用共享候选语义，不能形成独立阈值或排序实现。

## 功能合同

### 资源与文本边界

共享 `SemanticResourceRetrievalService` 接受已经解析的 `SemanticQueryScope` 或等价内部 read scope，
不得自行扩大 Project/Ontology 范围。首版资源类型映射为：

| 检索资源 | Context kind | 索引来源 |
| --- | --- | --- |
| OWL/RDFS Class | `concept` | 当前 Ontology/derived 图中的资源元数据 |
| Named Individual/Entity | `instance` | 当前 data/derived 图中的资源元数据 |
| Object/Datatype/RDF Property | `relation` | 当前 Ontology 图中的资源元数据 |
| 当前活动 Rule Definition | `rule` | PostgreSQL Rule 与 current Definition |
| 当前活动 Operation | `operation` | 当前 Ontology RDF Operation 元数据 |

普通 statement/fact 不建立向量文档；Context Query 仍可通过现有词面和邻域路径返回 fact。每个资源
文档聚合并保留来源字段：

- 所有 `rdfs:label` 及语言；
- 所有 `skos:altLabel` 及语言；
- `rdfs:comment` / `dcterms:description` 及语言；
- IRI 本地名和 NFKC/casefold/CamelCase/下划线/连字符拆分 token；
- RDF type IRI 本地名及可用 label；
- 显式指向资源的 `op:SemanticMapping` external field 本地名、join key、target type 和 Mapping ID；
- Rule 的当前 name、description、language 和 rule IRI；Operation 的 name、aliases、description、
  operation ID 和 target resource type 名称。

Mapping、label 和 alias 的原始值单独保存，用于返回依据；Embedding 输入使用确定字段顺序和长度
上限。任何缺少明确治理边界的 literal、Evidence、审计和查询正文都不进入文档。

### 请求与候选流程

Context Query 和接入的 read model 增加 `search_mode=hybrid|lexical`，默认 `hybrid`。`hybrid` 固定执行：

1. 解析并冻结本次授权 Ontology、workspace version、source signature、资源/assertion 过滤。
2. 使用现有规范化和显式字段规则生成词面候选；不再把任意 fact literal 加入共享资源索引。
3. 对规范化查询调用一次 Embedding provider；不得持久化查询文本或 query vector。
4. 只在授权 Ontology、精确 workspace version、source signature、rule-set signature、config hash、
   projection version、visibility 和资源类型过滤后的 current 文档上执行 pgvector exact cosine
   scan。v1 不使用 HNSW/IVFFlat，避免 ANN post-filter under-recall 被误报为完整 no-match。
5. 丢弃 cosine `<0.45` 的向量项，按 `(ontology_id, iri, resource_kind)` 合并词面和向量候选。
6. 精确 label、altLabel、Mapping、稳定 ID 形成 `exact` 证据层；其余候选按版本化 rank score 排序，
   再使用 Ontology 顺序、kind 顺序、规范化 label、稳定 ID tie-break。
7. 没有 exact 唯一依据且前列候选的有效分差 `<=0.03` 时标记 `ambiguous`，不删除低一名候选。
8. Context Query 对最终 primary candidates 继续执行现有关系/shape/operation 邻域与 lineage 装饰；
   Entity/Class adapter 只投影各自已存在的 UI/read-model 字段。
9. 返回时再次确认范围 workspace version 未变化；变化则返回稳定 `scope_version_changed`，调用方
   重新读取，不能把不同版本拼成一个结果。

`lexical` 跳过步骤 3–5，用于诊断和 provider 故障时显式复现。`hybrid` 中 provider 超时、错误，或
任一 Ontology 索引不可用时不得失败整个查询：保留词面结果，为对应 Ontology 标记 degraded。

### 排序和歧义

现有 `match.score` 继续作为稳定整数 rank score，保留兼容性；同时公开组成信号：

- `lexical_score`：现有 1–1000 整数规则；
- `semantic_similarity`：cosine `0..1`，只在模型/config/version 明确时返回；
- `candidate_level`：`exact | lexical_candidate | semantic_candidate`；
- `method`：`label | alt_label | mapping | identifier | description | semantic | mixed`；
- `reasons`、`matched_fields`、`matched_terms`：延续现有字段并增加稳定语义原因码。

Exact 证据层始终排在仅候选层之前。候选层 rank score 使用
`rank_score = max(lexical_score, round(semantic_similarity * 1000))`；缺失信号为 0。公开
`effective_score = rank_score / 1000`，固定保留三位小数，歧义分差 `0.03` 等价于 30 个 rank
points。该公式、阈值 `0.45`、分差、kind 顺序和文档模板共同属于 `semantic-retrieval-v1`。换模型
或算法必须新建版本，不允许在同一版本下静默调整。

歧义判定固定为：多个 exact 稳定 ID 一律 ambiguous；没有 exact 时，在同一过滤结果集中所有
`effective_score >= 0.45` 的候选按稳定顺序排列，Top-1 与任一后续候选相差 `<=0.03` 时保留这些
候选并标记 ambiguous。Lexical-only 使用 `lexical_score / 1000`，semantic-only 使用三位小数
cosine，mixed 使用上述 max；31 个及以上 rank points 不触发分差歧义，但候选仍可返回。

歧义以最终候选层和稳定 ID 判断，不把相同 label、相同向量或相同 IRI 跨 Ontology 合并。资源的
RDF type 必须返回，消费方可以区分 Workflow Definition、Run、Log、Published Workflow 和 Node；
平台不根据问题措辞猜测唯一业务角色。

## 公共接口

### Context Query

请求兼容增加：

```json
{"search_mode": "hybrid"}
```

原有 `result_status=matched|no_match` 保持。响应增加：

```json
{
  "recall": {
    "mode": "hybrid",
    "match_status": "exact|candidate|ambiguous|no_match",
    "completeness": "complete|degraded",
    "indexes": [
      {
        "ontology_id": "...",
        "workspace_version": "...",
        "status": "current|missing|stale|failed|config_mismatch|unavailable",
        "projection_version": "semantic-retrieval-v1",
        "embedding_model": "embedding-3",
        "embedding_config_hash": "..."
      }
    ]
  }
}
```

`primary_matches[*].match`/`related_context[*].match` 兼容增加 `method`、`candidate_level`、
  `lexical_score`、`effective_score` 和可选 `semantic_similarity`。`ambiguous_match` 继续作为 warning；新增
`semantic_recall_degraded`、`vector_index_missing|stale|failed|config_mismatch`。未授权 Ontology
不得出现在 indexes 或 warning 中。

当没有候选时仍返回 `result_status=no_match`。若 completeness 为 degraded，调用方只能得出“当前
可用路径未命中”，不能把它解释为完整检索已证明知识不存在。

### Entity 与 Class 搜索

- `entity-search` read model 的 `q` 默认通过共享 service 使用 hybrid；保留 `search_mode=lexical`。
  返回原有 Entity row 并增加 match/recall 状态，不改变 detail 读取。
- Class 页面输入不再只做前端 substring。非空查询调用 concept-filtered 共享召回 adapter，返回的
  Class 稳定 IRI 用于筛选/高亮已经加载的 topology；清空查询恢复完整 topology。候选不是 Class
  时不得混入 Class 结果。
- REST 与 MCP Context Query 调用同一服务和配置；不新增独立万能搜索工具。运行时 registry、API、
  MCP 和 platform guide 在产品实现时同步。

## 持久化与索引生命周期

### PostgreSQL/pgvector

部署镜像改为 pgvector-enabled PostgreSQL 17。Alembic migration：

- 验证并 `CREATE EXTENSION IF NOT EXISTS vector`；词面 contains 索引需要时启用 `pg_trgm`；
- 新增 retrieval document 表，至少保存 Ontology/Graph Set 内部归属、workspace version、source
  signature、resource IRI/kind、assertion kinds、原始 labels/aliases/descriptions/Mapping evidence、
  normalized text/tokens、text hash、`vector(1024)`、model、config hash、projection version、visibility、
  rule-set signature、
  build job 和时间；
- 唯一键约束同一版本资源文档，组合 B-tree/词面索引优化授权、版本、kind 和确定性 contains。
  在线向量查询在 SQL `WHERE` 完成授权/版本/signature/kind 约束后使用 exact cosine ORDER/LIMIT；
  v1 不创建 HNSW/IVFFlat，也不启用无合同的拼写模糊合并。

Migration 不调用外部 API。若服务器没有 vector extension，upgrade 明确失败并给出安装前置条件，
不能静默建成无向量能力的同名 schema。

### 构建与提升

真实 `PgVectorWriter` 替换运行时 Fake writer，但测试可继续注入 fake。构建固定：

1. 读取一个 Ontology 当前 workspace/Graph Set 快照和活动 Rule Definition；对按稳定 ID 排序的活动
   Rule ID、current Definition ID 及所有被索引字段做规范 JSON 序列化并计算 rule-set signature。
2. 生成确定性 metadata documents；以 text hash 跳过同 config 下无需重新 embedding 的文档。
3. Provider 默认每批 16 条，校验响应数量、每条 1024 维、有限数值和 config hash。
4. 写入 job 专属新分区；中途失败不触碰 current manifest。
5. 重读 workspace version、source signature、完整 rule-set signature 和派生 pointer；任一变化则
   job 标记 stale/conflicted，不提升。
6. 在 PostgreSQL 事务中提升 manifest；后续安全删除不再被 manifest 引用的旧分区。

首次上线使用显式、可重试 backfill 命令遍历 queryable Ontology，创建/运行现有 projection jobs。
它必须支持按 Ontology 重试、幂等、失败汇总和不打印索引文本；不绑定 Alembic 或服务启动。

### 同步写入合同

以下改变当前资源文本、类型或可见性的成功路径调用统一 index coordinator：建模批次
apply、governed semantic/canonical edit、导入/工作空间替换、Rule 当前定义切换、Operation 变更，
以及会改变 current 派生类型的 Rule/Reasoning pointer 提升。

RDF 路径先提交权威事实，再标记旧 manifest stale 并同步创建/运行重建 job；查询同时依靠 workspace/
source signature 阻止旧分区。Rule create/PATCH/DELETE 则必须重构现有 service/handler 事务边界：
Rule 变更与受影响 manifest stale 使用同一个 SQLAlchemy session/同一 PostgreSQL 事务提交，提交后
才运行外部 embedding。检索查询每次计算活动 rule-set signature；即使进程在提交后、重建前退出，
旧 Rule 文档也因 signature mismatch 不可查。

写响应增加检索索引结果：

- `current`：返回 job、workspace version、projection version；
- `failed|stale`：事实仍视为已应用，返回稳定 warning、job ID 和公开重建入口；
- 不允许返回普通 validation failure 或尝试删除已提交 RDF 来伪造回滚。

已有 Rule POST/PATCH 的 `SemanticRuleDefinitionRead` 兼容增加可选 `retrieval_index`；DELETE 继续返回
204，但固定通过 `X-Semantic-Write-Applied: true`、`X-Retrieval-Index-Status`、可选
`X-Retrieval-Index-Job-Id` 和 admin-only rebuild `Link` header 表达结果。POST/PATCH 同样返回这些
headers，旧客户端可忽略；MCP mutation（若后续暴露）使用等价结构化字段。索引失败不改变 2xx
写入结论。重建入口按 `ontology_id` 授权，不向消费 Agent 暴露内部 Graph Set。

一次写影响多个 Ontology 时逐项返回状态；无权调用方不能通过重建入口扩大 Ontology 范围。

## 配置、失败与安全

- 复用 OpenAI-compatible `EmbeddingClient`，但 query/build 超时和 build batch size 分开配置；v1
  默认模型 `embedding-3`、维度 1024、build batch 16、threshold 0.45、margin 0.03。
- Config hash 包含 provider identity（不含密钥）、model、dimensions、文档模板版本、归一化版本、
  threshold、margin 和融合版本。配置变化使旧 manifest `config_mismatch`。
- Query embedding 超时或 provider 5xx/4xx、返回数量/维度/数值非法均转为 vector unavailable；不
  回显 provider 原始 payload、URL secret 或输入文本。
- SQL 必须先按 resolver 输出的授权 Ontology/版本/kind/visibility 过滤，再执行近邻；不能先全库
  Top-K 后从响应删除无权结果。
- exact scan 达到独立 query timeout 时返回 vector unavailable/degraded；不得返回 complete no-match。
  v1 不通过调大未证明安全的 ANN scan 参数换取性能。
- 查询文本和 query vector 只存在请求内存；常规日志只记录范围 ID、模式、索引状态、耗时、候选
  数和 warning，不记录正文。

## 发布和兼容性

1. 先发布 pgvector PostgreSQL 镜像和 schema migration，验证现有同主版本数据卷；固定支持 exact
   search 的扩展版本，不依赖 ANN iterative scan。
2. 发布真实 writer、shared service 和兼容字段；所有索引尚 missing 时查询保持 lexical degraded。
3. 运行 existing-data backfill，逐 Ontology 验证 current/version/config 后再执行跨语言验收。
4. 接入同步写路径和 Entity/Class 默认 hybrid；观察 provider/索引失败，不以降级状态标记需求完成。
5. 独立 PASS、完整回归、重启和公开 REST/MCP/UI 验收后，才更新 R1.2-003/R-103 相关状态。

旧客户端忽略新增字段仍可按 `result_status` 工作；`search_mode` 未传时结果集可能因默认 hybrid
扩大，但现有 exact 词面项保持更高证据等级和稳定 ID。需要历史词面行为的客户端显式传
`lexical`。

## 验收映射

- 中文/混合语言/标识符变体：共享 service 和真实 embedding/pgvector 集成测试。
- exact/candidate/ambiguity/no-match：固定正反例 corpus、阈值和分差边界测试。
- 范围、版本、授权、防枚举：resolver + repository + REST/MCP 安全测试。
- missing/stale/failed/config mismatch：降级合同与词面回归测试。
- 同步重建/事实优先/并发变化：真实 PostgreSQL/Oxigraph/provider fake-failure 测试。
- Entity/Class 默认 hybrid：read-model 和 Playwright 验收。
- 部署：pgvector migration、existing volume、backfill、systemd restart 和健康检查。

## 实现完成门禁

设计文档存在不代表需求完成。R1.2-003 只有在产品实现、计划审查处置、共享测试计划独立 PASS、
existing-data backfill、完整 backend/frontend 回归、systemd 重启/真实接口验收、文档状态同步和
提交闭环全部完成后才能标记 `已实现`。
