# R-006 面向 Agent 的结构化语义上下文查询设计

## 1. 状态与目标

实现状态：`已实现`（2026-07-16，独立测试 Round 2 `PASS`）。

本设计细化 `docs/requirements-v1.0.md` 的 R-006，承接 R-001 默认语义工作区、R-005 统一
lineage 和现有只读 SPARQL 能力。

目标是让外部消费 Agent 在一个 Project 内选择全局范围或一个至多个 Ontology，提交任意非空
查询文本，并通过同一套确定性召回流程获得结构化语义上下文。平台只返回已有知识及其客观
状态，不调用 LLM，不生成最终答案，不判断结果是否足以回答问题，也不指导 Agent 下一步操作。

同一范围还提供 Agent 自行生成的只读 SPARQL 高级查询。自然语言召回和 SPARQL 都由平台解析
内部 Graph Set；普通 Agent 不提交 Graph Set ID 或 graph IRI。

## 2. 设计原则

1. **一个统一召回流程。** 不识别或分派“问题类型”；关键词、业务短语和完整问题走同一流程。
2. **业务范围在外，图范围在内。** 请求只使用 Project 和 Ontology，平台解析当前默认工作区。
3. **当前状态优先。** 首版只查询当前语义状态；历史和不可变 release 分别由 lineage/history
   和 R-105 负责。
4. **返回上下文，不返回答案。** 主要匹配与关联上下文分开，保持原始结构、稳定标识和状态。
5. **证据按需读取。** 上下文只返回 Evidence Reference ID 和状态，不返回文档名或原文。
6. **确定性和有界。** 排序、截断和警告可重放；查询、关系深度和结果数量都有上限。
7. **首版保持轻量。** 复用当前 RDF/PostgreSQL 数据和服务，不新增迁移、搜索索引、Embedding、
   向量库、消息队列或 LLM 依赖。
8. **REST/MCP 共用服务。** 两个入口不得复制范围解析、召回、排序或证据装饰逻辑。

## 3. 范围

### 3.1 首版包含

- Project 全局与显式一至多个 Ontology 两种查询范围。
- 中文、英文、中英文混合业务词和 API 标识符的词法召回。
- 名称、别名、描述、稳定标识、事实属性和值、关系、规则及已有 Operation 的召回。
- 当前 asserted 和当前 derived 内容；过期的当前派生结果带警告返回。
- 可选资源类型、断言类型、关系深度和数量过滤。
- 主要匹配与扁平化关联上下文、一层默认邻域和最大三层显式展开。
- R-005 lineage 状态与 Evidence Reference ID 的精简投影。
- 只读 SPARQL `SELECT`、`ASK`、`CONSTRUCT`、`DESCRIBE` 的范围限制。
- REST、MCP、API/MCP 文档、后端测试、现有 SPARQL Debug UI 调用兼容和真实运行时验收。

### 3.2 首版不包含

- 问题类型分类、意图路由、答案充分性判断或自然语言答案生成。
- 自动翻译、同义词生成、查询改写建议或推荐 SPARQL。
- Evidence 原文、Agent rationale、Edit Audit 备注或 Competency Question 的全文召回。
- 不同 Ontology 之间的定义合并、冲突裁决或未声明概念等价推断。
- 查询时执行新的推理、规则、复杂统计、假设推演或外部工具操作。
- 历史/发布版本查询；分别属于现有 lineage/history 和 R-105。
- 持久 Search/Vector 投影和混合召回；属于 R-103。
- 新的普通用户查询页面；Context Query 调试页属于 R-009。
- 查询审计和质量趋势；属于 R-108。
- R-008 的服务身份和细粒度授权实现，但本需求仍校验 Project/Ontology 归属并限制实际图范围。

## 4. 查询范围

新增 `SemanticQueryScopeResolver`，供结构化上下文查询和 SPARQL 共用。

### 4.1 请求范围

```json
{
  "project_id": "project-id",
  "scope_mode": "project",
  "ontology_ids": []
}
```

- `scope_mode=project`：`ontology_ids` 必须为空；按稳定顺序读取 Project 下全部 Ontology。
- `scope_mode=ontologies`：`ontology_ids` 必须包含一至多个唯一 ID；全部 ID 必须属于同一 Project。
- 请求不得包含 Graph Set ID、graph IRI 或 Dataset 地址。

### 4.2 解析结果

每个可查询 Ontology 通过 `OntologyWorkspaceService.context()` 解析默认 Graph Set，再通过
`SemanticReadScopeResolver` 取得 asserted、shape、当前 reasoning 和当前 rule 图；通过
`ModelingWorkspaceVersionService` 取得 `workspace_version`。

高级 SPARQL 的 dataset 只包含默认 Graph Set 的持久成员和当前派生结果指针。非成员的
`shapes/{ontology_id}/custom` 子图和从 asserted ontology 运行时计算的 generated guidance 不属于
原始 SPARQL dataset；合并后的 custom/generated SHACL 约束由 Context Query 通过 Shape Endpoint
投影。这样 SPARQL 范围、`source_signature` 和工作区版本保持同一契约。

解析结果只在服务内部保存图 IRI，对外返回：

- `ontology_id`；
- `workspace_version`；
- `source_signature`；
- 当前 reasoning/rule 状态与 run ID；
- 客观 warning。

### 4.3 完整性语义

- Project 全局模式允许排除未就绪 Ontology，返回 `scope_status=partial` 和排除清单。
- 显式 Ontology 模式必须完整成功；任一目标不存在、不属于 Project 或工作区未就绪时整体拒绝。
- 跨 Project ID 使用 `not_found` 或等价不泄漏响应，不返回目标 Project/Ontology 细节。
- 过期的当前派生指针不排除 Ontology；内容可以参与召回，但保留 stale warning。

## 5. 结构化上下文协议

### 5.1 REST 请求

```text
POST /api/semantic/context:query
```

```json
{
  "project_id": "project-id",
  "scope_mode": "ontologies",
  "ontology_ids": ["ontology-a", "ontology-b"],
  "query": "发布工作流需要哪些参数",
  "resource_types": ["concept", "instance", "relation", "fact", "rule", "operation"],
  "assertion_types": ["asserted", "derived"],
  "depth": 1,
  "limit": 20
}
```

约束：

- `query` 去除首尾空白后长度为 `1..2000`；
- `ontology_ids` 在显式模式下最多 50 个；
- `depth` 为 `0..3`，默认 `1`；
- `limit` 为 `1..100`，默认 `20`，同时约束主要匹配和关联上下文的总预算；
- 未提供类型过滤时查询全部当前知识类型；
- 首版不提供 cursor 分页，达到预算时返回 `truncated=true`。

### 5.2 响应

```json
{
  "query": {
    "text": "发布工作流需要哪些参数",
    "normalized_terms": ["发布工作流", "工作流", "参数"]
  },
  "result_status": "matched",
  "scope": {
    "project_id": "project-id",
    "mode": "ontologies",
    "status": "complete",
    "ontologies": [],
    "excluded_ontologies": []
  },
  "primary_matches": [],
  "related_context": [],
  "truncated": false,
  "warnings": []
}
```

- `result_status` 只有 `matched | no_match`；平台不返回“问题不支持”。
- 多个合理含义作为多个 `primary_matches` 返回，可附 `ambiguous_match` warning，但不是另一条流程。
- `scope.status` 独立表达 `complete | partial`，不得与是否命中混为一谈。
- warnings 使用稳定 code 和简短 message，不返回下一步操作建议。

### 5.3 上下文 Item

首版使用一个紧凑公共结构，避免为每种知识建立深层嵌套协议：

```json
{
  "id": "stable-resource-or-statement-id",
  "kind": "concept",
  "ontology_id": "ontology-id",
  "iri": "https://example.test/Workflow",
  "label": "工作流",
  "aliases": ["Workflow"],
  "description": "...",
  "data": {},
  "distance": 0,
  "assertion_type": "asserted",
  "assertion_kind": "asserted",
  "evidence_reference_ids": ["evidence-id"],
  "evidence_status": "supported",
  "lineage": {
    "target_type": "resource",
    "target_id": "https://example.test/Workflow",
    "status": "complete"
  },
  "derived_state": null,
  "match": {
    "score": 900,
    "matched_terms": ["工作流"],
    "matched_fields": ["label"],
    "reasons": ["exact_label"]
  },
  "warnings": []
}
```

- `kind` 为 `concept | instance | relation | fact | rule | operation`。
- `data` 只承载该 kind 的已有结构化字段，例如 fact 的 subject/predicate/object、relation 两端、
  rule 的稳定定义版本或 Operation 参数约束；不得放入证据原文、rationale、Audit 或问题文本。
- `distance=0` 表示直接匹配；关联上下文使用 `1..depth`。
- 同一稳定 ID 在一个列表中只出现一次；跨 Ontology 不合并不同资源。
- 同一 IRI 在多个 Ontology 中出现时仍保留各自 Ontology item，避免丢失来源和版本状态。

## 6. 统一召回流程

新增 `SemanticContextQueryService`。REST 和 MCP 都只负责 schema 转换与错误映射。

### 6.1 固定流程

1. 校验请求并解析 Project/Ontology 范围。
2. 对查询文本做确定性规范化并生成有限词项。
3. 在全部选中当前语义图上执行同一套 lexical candidate 查询。
4. 补充当前 Rule Definition 候选；R-007 落地后在同一步补充 Operation，不新增操作专用流程。
5. 应用调用方显式 resource/assertion 过滤。
6. 对候选进行确定性评分、去重和稳定排序。
7. 选择主要匹配，并在同一图范围内按请求深度展开关系、事实和约束。
8. 只对最终保留项投影 R-005 lineage、Evidence Reference ID、派生和过期状态。
9. 组装 scope、主要匹配、关联上下文、截断和 warnings。

无论查询文本看起来像定义、事实、关系、来源、统计或假设问题，都执行上述流程。服务不得根据
疑似问题类型切换模板或返回 `unsupported_question`。

### 6.2 查询文本规范化

首版只使用标准库：

- Unicode NFKC；
- `casefold()`；
- 空白和常见标点切分；
- camelCase、snake_case、kebab-case 和路径/API 标识符切分；
- 中文连续文本保留完整片段，并生成长度 `2..6` 的有限 n-gram；
- 去重后限制词项总数，优先保留较长、较具体、在原文中靠前的词项。

响应返回实际参与召回的 `normalized_terms`。此步骤不翻译、不生成同义词、不识别意图。

### 6.3 RDF 候选

在 `semantic_sparql_templates.py` 增加版本化模板：

- `semantic-context-candidates`：匹配 label、SKOS alias、description/comment、IRI、本体属性名称、
  literal fact value 和 relation label；返回 source graph 以映射 Ontology 和 assertion kind。
- `semantic-context-neighborhood`：以主要匹配 IRI 集合为锚点，读取入边、出边、literal fact、类型、
  label/alias 以及相关 predicate 定义。

模板必须使用服务器提供的 `VALUES` graph scope 和安全 RDF literal/IRI 序列化；调用方文本不得
直接拼接为 SPARQL 语法。shape graph 中的 SHACL 约束通过现有 Shape Endpoint 对最终匹配类/实例
按需读取，不全量扫描或建立第二套约束存储。

属性或关系 label 可以与使用该 predicate 的事实位于同一 Ontology 的不同持久图。候选模板必须
使用服务器生成的 graph-to-Ontology 绑定只在同一 Ontology 内关联 predicate label，不得因不同
Ontology 使用相同 predicate IRI 或相同 label 而错配事实所属范围。

### 6.4 PostgreSQL 候选

Rule Definition 当前权威数据在 PostgreSQL。服务只读取所选 Ontology 的当前 Rule Definition，
对 name、Rule IRI、language 和稳定描述字段应用同一规范化词项与评分规则。

R-007 落地前没有 Operation 候选时正常返回空；不得创建空 Operation 表、假数据或 Dify 分支。
R-007 必须接入同一个候选集合和响应 Item，不增加 Operation 专用查询 API。

### 6.5 排序

排序使用整数分值和稳定 tie-breaker。建议基准权重：

| 命中 | 基准分 |
| --- | ---: |
| 完整规范名称 | 1000 |
| 完整别名 | 900 |
| 名称包含或词项高覆盖 | 750 |
| 别名包含 | 700 |
| 稳定标识/API 标识符 | 600 |
| 关系/属性名称 | 550 |
| 描述 | 450 |
| literal fact value | 400 |

当前内容不额外加分；stale current derived 使用固定降权但不隐藏。最终 tie-breaker 依次为：调用方
Ontology 顺序（Project 模式使用 Ontology 创建时间和 ID）、kind 固定顺序、规范化 label、稳定 ID。
返回 `match.reasons`，不得暴露内部 graph IRI。

### 6.6 邻域与预算

- 默认 `depth=1`；`depth=0` 只返回主要匹配。
- 使用稳定 BFS 扩展，最大三层；响应仍放入扁平 `related_context`，以 `distance` 表达层级。
- 只有选中范围内实际存在的 RDF 关系可跨 Ontology 连接；名称相同不产生关系或合并。
- 主要匹配优先占用预算，关联上下文使用剩余预算。
- 达到候选、邻域或最终 item 上限时设置 `truncated=true` 和稳定 warning，不生成继续查询建议。

### 6.7 Lineage 与 Evidence

最终 item 使用 `OntologyLineageService`/其 repository 读取当前 lineage，但只投影：

- `lineage.status`、target type 和 target ID；
- `evidence_reference_ids`；
- `evidence_status`、dependency evidence status 和 proof level；
- stale/partial/missing warnings。

必须显式丢弃 Evidence `document_name`、`excerpt`、`created_by`、Agent rationale、Competency
Question 和 Edit Audit 内容。lineage target 不存在时保留召回 item，标记 `lineage.status=missing`，
不能使整个查询失败。

## 7. 只读 SPARQL 高级查询

### 7.1 协议

沿用：

```text
POST /api/semantic/sparql:query
MCP semantic_sparql_query
```

请求增加与 Context Query 相同的 `project_id`、`scope_mode`、`ontology_ids`，并保留 `query`、
`timeout_seconds`、`result_limit`。旧的无范围调用不再作为 v1 Agent 契约；仓库内调用方必须同步。
`timeout_seconds` 范围为 `(0, 120]`，`result_limit` 范围为 `[1, 10000]`，REST 与 MCP 均由共享
service 校验。

响应保留标准 SPARQL result 和 format，并增加 scope、Ontology versions、`truncated`、warnings。
不转换为 Context Item，不执行 lineage 装饰，不生成自然语言。

### 7.2 只读与范围保护

- 使用 RDFLib SPARQL parser 确认操作是 `SELECT | ASK | CONSTRUCT | DESCRIBE`。
- 拒绝 SPARQL Update、`SERVICE` 联邦查询和调用方 `FROM`/`FROM NAMED` 数据集声明。
- 对已验证查询进行 query-form aware 顶层扫描：跳过 prologue、注释、IRI、字符串、子查询和嵌套
  括号，只在 `SELECT`、`ASK`、`CONSTRUCT`、`DESCRIBE` 各自合法的 dataset 位置注入服务器提供的
  `FROM`/`FROM NAMED`。graph IRI 必须由 RDFLib `URIRef.n3()` 序列化。
- 注入后的查询必须再次通过 RDFLib parser，且查询形式不得改变；定位歧义、解析失败或范围为空时
  fail closed。原始 Agent 查询在任何失败分支都不得直接执行。
- `GRAPH ?g` 和显式 `GRAPH <iri>` 只能看到服务器提供的允许 named graph；跨 Project 图返回空，
  不能绕过范围。
- `CONSTRUCT`/`DESCRIBE` 只返回临时查询结果，不写入 RDF Dataset。
- parser 校验和 dataset 注入后，使用同一顶层 scanner 将调用方 `LIMIT` 限制到
  `result_limit + 1`，没有顶层 LIMIT 时补入该值，再次解析后才执行；注释、字符串和子查询中的
  LIMIT 不得被修改。
- `result_limit` 同时是硬响应上限：`SELECT` 按 binding、`CONSTRUCT`/`DESCRIBE` 按 RDF triple
  限制；图结果仍需在执行后做 triple 级裁剪，因为一个 solution 可能构造多个 triple。只有实际
  丢弃结果时才返回 `truncated=true`。`ASK` 保持布尔结果。

Oxigraph 0.5.9 的 HTTP 参数解析会折叠重复的 `default-graph-uri`/`named-graph-uri`，无法完整表达
多 Ontology 数据集，因此不采用协议参数作为 v1 范围边界。真实 Oxigraph 测试必须覆盖单图和多图
default union、`GRAPH ?g`、显式越界 GRAPH、跨图 join，以及四种只读查询形式。

## 8. REST、MCP 与前端边界

### 8.1 REST/MCP

- REST schema 放入 `backend/app/api/schemas.py`，handler 保持薄层。
- Context Query 与 scoped SPARQL 共用 `SemanticQueryScopeResolver`。
- MCP `query_semantic_context` 调用相同 `SemanticContextQueryService`。
- MCP `semantic_sparql_query` 改为同一 scoped SPARQL service。
- MCP registry、surface allowlist、`docs/api.md` 和 `docs/mcp.md` 必须同步。

### 8.2 前端

R-006 不实现 Context Query 页面，也不改造 Agent Test；该工作属于 R-009。

现有 Semantic Import/Export Debug 页仍调用 SPARQL，因此只做兼容性修改：从当前 workspace 传入
Project ID 和 Ontology ID，不新增面向普通用户的查询范围 UI，不再以 Graph Set 作为 Agent SPARQL
范围。Graph Set selector 继续服务于现有 export/debug 功能。

## 9. 错误与 warning

请求级错误：

- `invalid_query`：空白、过长或 SPARQL 语法/只读约束不满足；
- `invalid_scope`：范围模式与 Ontology 列表不匹配；
- `scope_not_found`：Project/Ontology 不存在或不属于请求 Project；
- `scope_not_ready`：显式 Ontology 范围存在未就绪工作区；
- `query_timeout`：底层查询超时；
- `query_unavailable`：RDF 查询存储暂时不可用。

响应 warning 至少包括：

- `scope_partial`；
- `ontology_workspace_excluded`；
- `derived_result_stale` / `derived_result_missing`；
- `ambiguous_match`；
- `context_truncated`；
- `lineage_partial` / `lineage_missing`；
- `evidence_missing`。

warning 只报告客观状态，不包含“应该继续查询什么”的建议。

## 10. 文件与实现顺序

建议新增：

- `backend/app/services/semantic_query_scope.py`
- `backend/app/services/semantic_context_query.py`
- `backend/app/services/scoped_sparql_query.py`
- `backend/tests/test_semantic_context_query.py`
- `backend/tests/test_semantic_context_query_api.py`
- `backend/tests/test_semantic_context_query_mcp.py`
- `backend/tests/test_scoped_sparql_query.py`

建议修改：

- `backend/app/api/schemas.py`
- `backend/app/api/semantic.py`
- `backend/app/mcp/tools/semantic.py`
- `backend/app/repositories/rdf_store.py`
- `backend/app/services/semantic_sparql_templates.py`
- `backend/tests/test_mcp_surface.py`
- `frontend/src/types.ts`
- `frontend/src/semanticApi.ts`
- `frontend/src/pages/SemanticImportExportPage.tsx`
- `frontend/src/App.tsx`
- `docs/api.md`
- `docs/mcp.md`
- `docs/architecture.md`

实现顺序：

1. 公共 scope schema/resolver 与单元测试。
2. 统一词项、候选、排序和邻域服务。
3. lineage/evidence 精简装饰。
4. REST/MCP Context Query。
5. scoped SPARQL repository/service、REST/MCP 和越界测试。
6. 现有前端 SPARQL 调用兼容。
7. 文档、全量测试、真实运行时和服务重启。

## 11. 完成条件

- 自然语言请求不经过问题类型分派，四类验收场景由同一服务完成。
- 中文、英文、混合 API 标识、别名、fact value 和关系邻域均有确定性测试。
- Project 全局部分范围、显式列表全有或全无、跨 Project 防泄漏均通过。
- 主要匹配和关联上下文分离，默认一层，排序和 warning 可重放。
- Evidence 只返回 ID/状态，任何 Context Query 响应都不含 evidence excerpt、rationale、Audit 或
  Competency Question 内容。
- SPARQL 四种只读查询可用，Update/SERVICE/FROM 被拒绝，图范围不能绕过。
- REST/MCP 核心结果一致；现有 Debug SPARQL 调用正常。
- 无数据库迁移、Search/Vector/LLM 新依赖或 R-009 页面范围扩张。
- 定向测试、backend 全量 pytest、frontend build、Playwright、真实 PostgreSQL/Oxigraph 验收和
  `ontology-platform.service` 重启健康检查全部通过。

## 12. 实现结果

R-006 已按本设计交付。`SemanticQueryScopeResolver` 统一解析 Project 全局或显式一至多个
Ontology 的当前默认工作区；`SemanticContextQueryService` 为 REST/MCP 提供同一套确定性召回、
排序、邻域和精简 lineage/Evidence 投影；`ScopedSparqlQueryService` 为四类只读 SPARQL 提供
相同范围、解析器校验的 fail-closed dataset 注入、顶层 LIMIT 收紧和硬结果上限。

最终服务边界保持不变：平台返回结构化上下文而非答案，Evidence 仅返回 Reference ID 和状态，
普通 Agent 不提交 Graph Set 或 graph IRI。raw scoped SPARQL 仅包含默认 Graph Set 的持久成员和
当前派生指针；非成员 `/custom` 与运行时生成的 SHACL guidance 不进入 raw SPARQL 范围，由
Context Query 的 Shape Endpoint 合并投影。R-009 页面、R-008 身份认证和细粒度授权、R-103
持久检索投影不在本需求内。

独立测试计划
`docs/superpowers/plans/2026-07-16-r006-semantic-context-query-test-plan.md` 的 Round 2 结论为
`PASS`，无阻塞缺陷；backend 全量、frontend build、Playwright、真实 PostgreSQL/Oxigraph 和
服务重启健康检查均通过。
