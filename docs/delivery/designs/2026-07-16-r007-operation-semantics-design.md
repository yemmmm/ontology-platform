# R-007 通用操作语义与外部工具绑定设计

## 1. 状态与决策摘要

实现状态：`已实现`（2026-07-16，plan review Round 2 `PASS`，独立测试 Round 2 `PASS`）。

本设计细化 `docs/requirements/requirements-v1.0.md` 的 R-007，承接 R-004 Modeling Batch、R-005 统一
lineage 与 R-006 Context Query。基于 R-001 至 R-006 的既有边界，R-007 做以下收敛：

1. Operation 是 Ontology 内的当前语义知识，权威状态位于默认 `asserted_ontology` 图。
2. 写入扩展 R-004，查询扩展 R-006；不新建 Operation 专用 REST/MCP 入口。
3. R-005 自动提供语句、Modeling Item、Evidence 和 Audit lineage；不建 Operation 历史表。
4. 平台只描述外部能力，不执行工具、不保存凭证实例、不判断某次调用是否满足前置条件。
5. 首版使用一个 Operation RDF 资源加受控 JSON literals 表达有界集合，避免双存储、孤儿子节点和
   一套新的版本系统。该编码带 `schema_version=operation-v1`，未来可迁移为更细粒度 RDF 节点。

## 2. 目标与非目标

### 2.1 目标

- 用通用领域模型表达 Operation、参数、条件、效果、失败、幂等性、风险、工具绑定和凭证需求类型。
- 支持 R-004 `create_operation`、`update_operation`、`delete_operation` 的 dry-run/apply/recovery。
- 支持受治理 RDF 编辑创建或更新相同 Operation，并共享不可绕过的领域校验。
- 在 R-006 同一候选与响应中召回 Operation，并返回目标资源与完整结构化当前态。
- 保持 REST/MCP、Evidence/lineage、Project/Ontology scope 和确定性排序一致。

### 2.2 非目标

- 外部工具执行、调用编排、重试补偿、运行日志或审批。
- 凭证实例、secret storage、认证授权或 RBAC。
- 可执行条件语言、自动规划、LLM 意图分类或答案生成。
- Operation UI、Dify 专用包、实例同步或发布版本查询。

## 3. 领域契约

### 3.1 Operation

活动 Operation 的公共结构：

```json
{
  "operation_id": "publish-workflow",
  "operation_iri": "http://ontology-platform.local/semantic/operation/publish-workflow",
  "name": "发布工作流",
  "aliases": ["Publish workflow"],
  "description": "发布一个处于草稿状态的工作流",
  "target_resource_type_iri": "https://example.test/class/Workflow",
  "parameters": [],
  "preconditions": [],
  "effects": [],
  "possible_failures": [],
  "idempotency": {"kind": "conditional", "description": "同一版本重复发布无副作用"},
  "risk_level": "medium",
  "tool_bindings": [],
  "credential_requirements": [],
  "status": "active",
  "schema_version": "operation-v1"
}
```

- `operation_id` 在一个 Ontology 内稳定；缺省时由 R-004 既有确定性 ID 规则生成。
- `operation_iri` 始终由平台 Operation namespace 和 `operation_id` 一一确定性生成；create payload
  不接受自定义 IRI。update/delete 可用 ID 或规范 IRI 定位；两者同时出现时必须严格匹配。
- direct RDF edit 中 Operation subject IRI 也必须等于其 `op:id` 对应的规范 IRI。这样无需额外表或
  migration 即可保证一个 Ontology 内 ID/IRI 一一对应，且相同 ID 不可能声明第二个合法 subject。
- `name`、`target_resource_type_iri`、`idempotency.kind`、`risk_level` 和至少一个
  `tool_binding` 是活动 Operation 必填项。
- `status` 只有 `active | inactive`。`delete_operation` 删除当前 RDF 语句；它不是硬删除 Audit 或
  Statement Occurrence。
- `risk_level` 只有 `low | medium | high | critical`；平台只返回事实，不据此执行审批。
- `idempotency.kind` 只有 `idempotent | conditional | non_idempotent | unknown`，description 可空。

### 3.2 参数与声明集合

参数：

```json
{
  "name": "workflow_id",
  "description": "目标工作流稳定标识",
  "required": true,
  "value_type": "string",
  "enum_values": [],
  "default_value": null,
  "constraints": {"min_length": 1, "max_length": 128, "pattern": "^[A-Za-z0-9_-]+$"}
}
```

- `value_type` 为 `string | integer | number | boolean | object | array | iri`。
- `constraints` 只允许 `min_value`、`max_value`、`min_length`、`max_length`、`pattern`、`format`；
  每个集合和字符串均使用服务常量限制容量，防止借 Operation 绕过 R-004 请求上限。
- 同一 Operation 参数名唯一。默认值必须匹配 value type，且若 enum 非空必须位于 enum 内。
- 前置条件与效果使用 `{name, description}`；可能失败使用
  `{code, description, retryable}`。名称/code 在各自集合内唯一。
- 首版不接受表达式、脚本、模板、URL 调用体或可执行代码。

### 3.3 工具绑定与凭证需求

工具绑定：

```json
{
  "binding_id": "dify-http-publish",
  "kind": "http_api",
  "system": "dify",
  "operation_identifier": "POST /workflows/{workflow_id}/publish",
  "version": "enterprise-v1",
  "documentation_source": "Dify Enterprise API guide",
  "documentation_version": "2026-07"
}
```

- `kind` 只有 `http_api | mcp_tool`；`operation_identifier` 是外部标识，不是可执行请求模板。
- `binding_id` 在 Operation 内唯一；`system` 是普通数据，`dify` 不触发代码分支。
- 文档来源/版本是非秘密元数据；建模原文仍通过 R-002 Evidence Reference 关联 Modeling Item。

凭证需求：

```json
{
  "name": "Dify API key",
  "reference_type": "api_key",
  "description": "调用方运行时提供",
  "required": true
}
```

- 允许字段固定为 `name`、`reference_type`、`description`、`required`。
- 任意层级出现 `credential_id`、`credential_ref`、`api_key`、`token`、`secret`、`password`、
  `authorization`、`header_value` 或等价 secret-bearing key 时拒绝整个 Item/直接 RDF 编辑。
- `reference_type` 是分类字符串，不得是凭证实例 ID、URL、header 或秘密值。

## 4. RDF 当前态

Operation 写入默认 `asserted_ontology` 图。词汇位于现有平台 vocab：

| Predicate | 值 |
| --- | --- |
| `rdf:type` | `op:Operation` |
| `op:id` | stable ID literal |
| `op:ontology` | Ontology IRI |
| `rdfs:label` | name |
| `skos:altLabel` | aliases，零至多值 |
| `rdfs:comment` | description，可选 |
| `op:targetResourceType` | Class IRI |
| `op:parameters` | canonical JSON literal |
| `op:preconditions` | canonical JSON literal |
| `op:effects` | canonical JSON literal |
| `op:possibleFailures` | canonical JSON literal |
| `op:idempotency` | canonical JSON literal |
| `op:riskLevel` | enum literal |
| `op:toolBindings` | canonical JSON literal |
| `op:credentialRequirements` | canonical JSON literal |
| `op:status` | enum literal |
| `op:schemaVersion` | `operation-v1` |

集合使用 `rdf:JSON` typed literal，序列化必须 UTF-8、key 排序、无无意义空白；同一业务内容因此得到
相同 quad、Batch delta 和 Statement ID。选择此编码是为了让 patch 可通过现有 wildcard predicate
replace 原子更新，不留下 RDF 子节点孤儿，也不引入 Postgres/RDF 双写。Context Query 返回已解析
结构，Agent 不需要解析 JSON literal。

Operation 词汇谓词和 required cardinality 是平台不变量：即使 `validate=false`，命令和直接 RDF
编辑也必须校验。目标资源必须在同一 Ontology 候选态中存在为 `owl:Class`；跨 Ontology 相同 IRI
不能借此绕过归属。

Operation JSON predicates 是内部承载细节，固定为 `op:parameters`、`op:preconditions`、
`op:effects`、`op:possibleFailures`、`op:idempotency`、`op:toolBindings` 和
`op:credentialRequirements`。R-006 的通用 RDF statement candidate 与 neighborhood 必须跳过这些
predicate，也必须跳过 `rdf:type op:Operation` 资源的通用 resource 投影；只有受控 Operation
candidate/serializer 可以解析并返回它们。该规则同样适用于 `resource_types=["fact"]`，防止 JSON
lexical form 作为 `data.object` 泄漏。

## 5. 写入协议

### 5.1 Modeling Batch

在 `ModelingCommandHandlerRegistry` 注册：

- `create_operation`：create resource，支持确定性 ID/IRI 和同批次 `item_ref` 目标 Class；不接受
  `operation_iri`。
- `update_operation`：用 `operation_id | operation_iri` 定位；scalar 省略保持，显式集合整体替换。
- `delete_operation`：删除 Operation 主语全部三元组；若其他资源引用该 Operation，不级联删除对方。

Operation handler 编译为现有 `RdfGraphDelta`，storage=`rdf`，因此自然复用 R-004 的冲突集合、候选
SHACL、幂等、partial apply、recovery、revision、stale 和 R-005 recorder。Operation 的写入效果键
按 `{ontology graph, operation IRI, predicate}` 归一化；同槽不同值必须触发
`conflicting_item_effects`，不能依赖 Item 顺序。

Operation payload 错误进入 Item `Validation Finding`：

| Code | 语义 |
| --- | --- |
| `invalid_operation_payload` | 字段、类型、枚举、容量或集合唯一性错误 |
| `operation_target_not_found` | 目标 Class 在候选 Ontology 中不存在 |
| `operation_not_found` | update/delete 目标不存在或不属于 Ontology |
| `operation_secret_forbidden` | 出现凭证实例或 secret-bearing 字段 |
| `unsupported_operation_schema_version` | 不是 `operation-v1` |

请求级 session、lease、workspace version、scope、idempotency 错误继续使用 R-004 既有语义。

唯一安全例外是 secret-bearing key：`ModelingBatchService.submit()` 必须在 `_get_or_create_batch()`
以及任何 `ModelingBatchModel` / `ModelingItemModel` 构造前，只对 `*_operation` payload 做递归 key
扫描。命中时立即抛出请求级 `operation_secret_forbidden`（HTTP 422），message/details 只报告存在
禁用字段，不返回 key path 的值；不得创建 Batch、Attempt、Item、Finding、content hash、Audit 或
日志 payload。编译期和 Operation codec 仍重复执行同一扫描，形成防御纵深，但不能替代前置门。

### 5.2 受治理 RDF 编辑

Turtle/TriG/JSON-LD、`INSERT DATA`、`DELETE DATA` 和确定性 delete/insert 可编辑 Operation。写入前：

1. 解析 affected graph 和候选 delta；
2. 识别被触及的 Operation IRI；
3. 合并当前图与 delta 得到候选 Operation；
4. 执行与 Modeling Batch 相同的 schema、目标 Class、secret 和 cardinality 校验；
5. 通过后再写 RDF、Audit、revision、stale 和 lineage。

影响 Operation 词汇但无法在执行前确定具体候选的 restricted `DELETE/INSERT WHERE` 返回
`operation_edit_not_deterministic`。非 Operation RDF 编辑保持现状。

## 6. Context Query 集成

`SemanticContextQueryService` 在现有 RDF candidates 与 Rule candidates 旁增加 Operation candidates，
仍执行同一个过滤、排序、去重、邻域、lineage 和响应组装流程。

- 范围只读取解析后的当前 graph-to-Ontology 映射；Operation graph 必须属于目标 Ontology。
- 候选匹配 name、alias、description、IRI、目标 Class label/IRI、参数、条件、效果、失败 code/描述、
  binding system/identifier/version 和 credential `reference_type`。
- public `data` 返回第 3 节结构，但不返回 RDF graph、原始 JSON lexical form 或任何秘密字段。
- `kind=operation` 的 lineage target 复用 `resource` + Operation IRI。
- 目标 Class 作为一层 `related_context`；Operation 不产生下一步建议，也不产生独立意图路由。
- inactive/deleted Operation 不参与当前候选；历史只能通过 lineage/history 能力读取。
- 通用 `_rdf_candidates()` 和 `_statement_item()` 必须排除 Operation type/resource 和内部 predicates，
  防止 raw JSON 作为 fact/relation 在未过滤或 `resource_types=["fact"]` 请求中出现；专用 candidate
  是 Operation 在 Context Query 中的唯一公共表示。

排序沿用 R-006 权重：Operation name/alias/IRI/description 与其他资源同权；集合字段匹配使用低于
description、高于普通 fact value 的稳定权重。相同分值使用 Ontology 顺序、kind 顺序、IRI 和 ID
tie-breaker。

## 7. 一致性、错误与安全

- REST/MCP 继续共用 R-004/R-006 service；MCP 不得绕过 payload、secret 或容量校验。
- Context Query 递归 public serializer 只允许 Operation schema 字段；不透传未知 RDF JSON key。
- R-008 完成前，现有接口仍没有服务身份安全保证。R-007 不声称外部接入安全，只保证自己的
  Operation payload/词汇不承载凭证实例。
- 任意直接 RDF 图仍可能被管理员写入与 Operation 无关的任意文字；通用 secret 扫描和接口授权是
  R-008 的仓库级安全门槛。R-007 的完成门槛是所有 Operation 命令、词汇和查询投影均 fail closed。
- 不创建 migration；RDF vocab 是向后兼容新增。服务重启后当前 Operation 从 Oxigraph 恢复。

## 8. 风险探针结论

1. **RDF JSON literal：通过。** 2026-07-16 在真实 Oxigraph 临时 named graph 写入并按
   `STR()`/`DATATYPE()` 查询 `rdf:JSON`，结果正确；临时图已删除并以 `ASK=false` 验证清理。
2. **批次与 lineage 复用：通过代码核对。** R-004 RDF handler 最终进入
   `CanonicalSemanticWriteService.apply_compiled_command()`，后者统一 bump revision、mark stale 并
   调用 `SemanticLineageRecorder.record_asserted_delta()`，无需 Operation 双写。
3. **直接编辑不可绕过：当前存在实现缺口。** `SemanticService.apply_edit()` 的 `validate=false` 只
   跳过 SHACL 且目前没有 Operation invariant。开发必须在 RDF update 前加入共享 Operation 校验；
   这是设计门槛，不允许以文档约束替代。

## 9. 交付面与验收

实现至少覆盖：

- Operation schema/validator/codec 与 canonical compiler；
- Modeling handler registry、R-004 apply/recovery/lineage 兼容；
- direct RDF edit invariant；
- R-006 Operation candidate、structured item、target Class related context；
- REST/MCP schema/surface 回归；
- API、MCP、architecture、glossary 和 requirement 状态同步；
- 共享测试计划中的自动化、真实 PostgreSQL/Oxigraph、重启和健康检查。

首版无 frontend 代码变更，因此不要求新页面或 Playwright 用例；若实现触及 frontend，则恢复执行
仓库规定的 `npm run build` 和全量 Playwright。

## 10. Plan review 记录

### Round 1 - 2026-07-16 - REVISE

- `accepted-high`：secret 校验原计划位于 Batch 持久化之后，无法满足不可变 Batch 不含 secret 的
  要求。已增加 `_get_or_create_batch()` 前的请求级 Operation payload 扫描和零持久化门槛。
- `accepted-high`：R-006 通用 literal candidate 会把 `rdf:JSON` 作为普通 fact 的 `data.object`
  返回。已要求通用 candidate/neighborhood 排除 Operation 资源与内部 predicate，专用 serializer
  成为唯一公共表示。
- `accepted-high`：自定义 Operation IRI 会允许同一 `op:id` 对应多个 subject，使 update/delete
  不确定。已取消 create 自定义 IRI，并要求 direct RDF subject 与平台 ID-derived IRI 严格一致。

修订后的设计与测试计划必须交回同一 `plan_reviewer` 复审；未取得 PASS 前不得开发。

### Round 2 - 2026-07-16 - PASS

- reviewer 确认 pre-persistence secret gate 已覆盖数据库、错误和日志验收。
- reviewer 确认 Operation 内部 JSON 已从通用 resource/fact/relation/neighborhood 路径排除。
- reviewer 确认 ID-derived IRI、create 禁止自定义 IRI及 direct/update/delete 一致性校验消除了歧义。
- 未发现新的 evidence-backed Critical/High 问题。

## 11. 冻结开发交接

- 需求：`docs/requirements/requirements-v1.0.md` R-007（本轮已细化，状态在独立 PASS 前保持未实现）。
- 设计：本文，plan review Round 2 `PASS`；Round 1 三项 High 均为 `accepted-high` 并已修订。
- 共享测试：`docs/delivery/test-plans/2026-07-16-r007-operation-semantics-test-plan.md`。
- 起始 HEAD：`b146983bbf23d8e8765bb8db0bb7f1e61679b9f3`。
- 起始工作区只包含上述 requirement/design/test-plan 三个 R-007 文档变更，无其他用户改动。
- 开发完成后至少执行定向 backend、全量 `uv run pytest`、changed-file Ruff check/format、
  `git diff --check`；不触及 frontend 时无需 UI suite。开发 Agent 不提交。

## 12. 实现结果

- 共享 `operation_semantics.py` 定义 Operation vocabulary、canonical JSON codec、ID-derived IRI、
  schema/capacity/type/secret 校验和 RDF candidate invariant。
- R-004 handler/compiler 接入 create/update/delete Operation；secret 请求在 Batch 持久化前拒绝，
  新 Ontology 尚无物理 asserted graph 时按正常空图处理，真实 store 错误不吞。
- canonical write 与 direct RDF edit 共用 Operation candidate 校验；`validate=false` 不绕过，显式
  Operation WHERE、含 Operation 当前态的通配 WHERE 和图检查失败均 fail closed，普通非 Operation
  ontology WHERE 保持可用。
- R-006 使用同一 scope/ranking/lineage pipeline 返回结构化 Operation 与目标 Class context；通用
  SPARQL candidate/neighborhood 和 service fallback 同时排除 Operation raw JSON 投影。
- API、MCP、architecture、glossary 和 requirements 已同步；无 Operation 专用 REST/MCP endpoint、
  Postgres 表、migration、frontend 或 Dify 产品分支。
- 独立测试保留 Round 1 `FAIL` 和修复后的 Round 2 `PASS`。最终证据为定向 `115 passed`、全量
  backend `646 passed, 3 skipped`、真实 PostgreSQL/Oxigraph 生命周期/安全/scope/重启/清理通过、
  restored `legacy_only` service active、backend/frontend 200。
