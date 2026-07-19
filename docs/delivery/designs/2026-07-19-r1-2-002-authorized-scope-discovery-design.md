# R1.2-002 Project 与 Ontology 授权范围发现设计

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-002
- Contract version: 2026-07-18 已确认的 13 项功能决定
- Status: implemented and independently verified (Round 2 PASS, 2026-07-19)

## 目标

为消费 Agent 提供独立的只读 REST/MCP 范围目录。调用方无需预先知道内部 ID，即可在当前身份
授权范围内定位 Project/Ontology、判断当前查询就绪性，并直接构造 R-006 Context Query 或 scoped
SPARQL 参数。平台不记录“是否先发现”的会话状态；已有明确范围的客户端仍可直接查询。

## 非目标

- 不搜索 RDF Dataset、Class、Entity、Relation、Rule 或业务事实。
- 不做多语言、模糊、同义词、拼写纠正或向量召回。
- 不返回 Build Session、建模进度、阻塞项或未决工作。
- 不暴露 Graph Set，不新增目录快照、目录 revision、Project `scope_version` 或历史版本选择。
- 不替消费 Agent 选择候选、编排后续调用或生成自然语言答案。
- 本需求不新增前端页面；公开消费合同为 REST 与 MCP。

## 功能合同

### 公开入口

- REST：新增 `GET /api/semantic/scopes:discover`，需要 `read` scope。
- MCP：新增 `discover_semantic_scopes`，参数和核心返回由同一服务实现。
- 输入：可选 `query`、可选 `queryable=true|false`、可选不透明 `cursor`、`limit`（默认 50，
  最小 1，最大 100）。空白 `query` 视为未筛选；超长、非法筛选、非法游标返回稳定的
  `invalid_discovery_request` 或 `invalid_cursor`。
- REST 由当前 `AuthPrincipal`、MCP 由运行时认证主体向服务传入 `authorized_project_id`；Project
  绑定凭证只能读取其 Project，组织管理员可读取全部 Project。服务永远先施加授权边界再筛选、
  排序和计数。

### 返回模型与分页

响应为有界的扁平候选流，避免一个 Project 下的 Ontology 数量绕过页面 `limit`：

```json
{
  "items": [
    {
      "resource_type": "project",
      "id": "...",
      "name": "...",
      "description": "...",
      "matched_on": ["name"],
      "query_status": "complete|partial|unavailable",
      "query_scope": {"project_id": "...", "scope_mode": "project", "ontology_ids": []},
      "excluded_ontologies": [{"ontology_id": "...", "reason": "..."}]
    },
    {
      "resource_type": "ontology",
      "id": "...",
      "project": {"id": "...", "name": "...", "description": "..."},
      "name": "...",
      "description": "...",
      "status": "draft|active|archived",
      "queryable": true,
      "unavailable_reason": null,
      "workspace_version": "...",
      "derived_warnings": [],
      "matched_on": ["name"],
      "query_scope": {"project_id": "...", "scope_mode": "ontologies", "ontology_ids": ["..."]}
    }
  ],
  "has_more": false,
  "next_cursor": null,
  "generated_at": "..."
}
```

Project 与 Ontology 分别计入 `limit`。稳定排序为 Project 的规范化名称、Project ID、资源类型
（Project 在前）、Ontology 的规范化名称和 Ontology ID；不透明 keyset cursor 记录最后排序键、
协议版本、筛选指纹及授权 Project 边界。cursor 只能用于相同 principal Project 边界和
`query`/`queryable` 条件；不认识、被篡改、跨授权边界或条件不匹配时失败，不退化为第一页。
配置 `SECRET_KEY` 时签名材料可跨进程/重启复用；未配置时使用进程私有随机材料，cursor 不承诺
跨进程或重启存活。分页读取当前目录，不承诺跨页快照一致；每页使用数据库当前时间生成
`generated_at`。

无 `query` 时，每个授权 Project 项及其授权 Ontology 项都进入逻辑全集。Project 名称或稳定 ID
命中时，Project 及其全部授权 Ontology 进入候选集；仅 Ontology 命中时，返回命中的 Ontology，
其内嵌父 Project 提供建立范围所需上下文，不额外增加未命中的 Project 候选项。Project/Ontology
同时命中时都保留。稳定 ID 只精确匹配；名称执行 trim 后的 Unicode `casefold` 包含匹配；
`matched_on` 只使用 `id`、`name` 或 `project`。重名全部保留，无匹配返回空成功页。

`queryable` 只筛 Ontology 候选；筛选存在时仅保留至少有一个匹配 Ontology 的 Project 候选。
显式 `queryable=false` 仍返回每个不可用 Ontology 的原因。Project 聚合状态和排除清单始终基于
该 Project 的完整授权 Ontology 集合，不因当前筛选而伪造状态。

### 查询就绪性

新增共享的 Ontology 查询就绪评估，供发现服务和 `SemanticQueryScopeResolver` 使用，避免目录
状态与实际查询分叉：

- `archived`：`queryable=false`、`unavailable_reason=ontology_archived`；Project 查询排除。
- `draft`/`active` 且默认工作空间 `state=ready`：`queryable=true`。
- 工作空间缺失、损坏或版本无法计算：`queryable=false`、
  `unavailable_reason=workspace_not_ready`。
- reasoning/rule pointer 为 missing/stale 时仍可查询；复用现有公开告警码
  `derived_result_missing`、`derived_result_stale`，不返回内部图 IRI。
- 不可查询 Ontology 的 `workspace_version` 为 `null`；可查询 Ontology 返回当前实际版本。

Project 有 Ontology 且全部可查询为 `complete`；至少一个可查询且至少一个不可查询为 `partial`；
没有 Ontology 或没有可查询 Ontology 为 `unavailable`。Project 范围查询继续只覆盖可查询
Ontology；显式 Ontology 范围包含任一不可查询项时返回 `409 scope_not_ready`；`unavailable`
Project 范围同样返回 `409 scope_not_ready`，不得返回看似成功的空语义结果。实际 Context/SPARQL
请求每次重新验证授权、生命周期、工作空间及版本。

### 授权与错误

- 缺少或无效认证保持 `401 invalid_authentication`；缺少 read scope 为 `403 forbidden_scope`。
- 目录查询只对已经过滤后的授权集合工作；用 `query` 输入外国 Project/Ontology ID 得到成功空
  集合，不暴露其存在性。现有显式 Project 资源路由的越权继续为 `403 forbidden_scope`，不能安全
  暴露归属的 Ontology 继续为 `404 scope_not_found`。
- MCP 工具注册为 read-only、身份感知的全局安全发现能力：Project 绑定凭证不需要在参数中重复
  暴露 Project ID，但服务必须使用认证主体的 `project_id` 限制结果。MCP 返回既有 `{ok,data}` /
  `{ok:false,error_code}` 包装，核心 `data` 与 REST 响应一致。

## 代码边界

- 新服务 `backend/app/services/authorized_scope_discovery.py` 拥有筛选、就绪评估、聚合状态、排序、
  cursor 和公共序列化；不复用 CRUD handler。
- `backend/app/api/semantic.py` 只校验 HTTP 参数、注入主体/服务依赖并映射服务错误。
- `backend/app/mcp/tools/semantic.py` 注册薄工具；`backend/app/mcp/runtime.py` 提供当前认证主体的
  只读访问器并登记工具策略。
- `backend/app/services/semantic_query_scope.py` 复用同一就绪评估，以落实 archived、partial 和
  unavailable 后续查询行为。
- Pydantic 请求/响应模型放在 `backend/app/api/schemas.py`；无数据库迁移。

## 发布与兼容性

新增入口不改变现有 CRUD 列表和已有 R-006 成功响应。语义范围解析只收紧此前错误允许的
`archived` 和全不可用 Project：它们改为稳定 `scope_not_ready`；部分 Project 仍保持原有排除
行为。MCP 工具清单、策略清单、API/MCP/platform guide 和 requirements 状态必须同步。

## 验收映射

- 授权全集、筛选、重名、空结果：服务与 REST/MCP 合同测试。
- complete/partial/unavailable、archived、损坏工作空间、派生 missing/stale：真实 SQLAlchemy
  服务测试，并覆盖 Context/SPARQL 范围解析回归。
- keyset 全量遍历、筛选指纹、目录跨页变化：分页边界测试。
- Project 凭证、组织管理员、外国 ID 查询、无认证/无 read scope：REST/MCP 授权测试。
- 返回的 `query_scope` 直接调用 Context Query 与 scoped SPARQL：公开接口集成测试。

## 实现结果

- 新增共享发现/就绪服务、REST/MCP adapter 和公开 Pydantic 响应模型，无迁移、无前端页面。
- R-006 `SemanticQueryScopeResolver` 复用相同就绪判断：archived 与损坏工作区不可查询，部分 Project
  保留排除清单，全不可用或空 Project 返回 `scope_not_ready`。
- MCP 工具使用 `read + global_safe + read-only` policy；Project-bound 主体由运行时认证身份限制目录，
  不要求在工具参数中重复 Project ID。
- 专项与独立回归覆盖授权过滤、metadata 筛选、分页/cursor、readiness、REST/MCP 一致性、认证、
  工具清单和既有查询范围。共享测试计划 Round 1 发现 cursor 身份边界和默认完整性材料缺陷；
  修复后 Round 2 独立 PASS，完整后端、前端、真实接口和重启门禁均通过。
