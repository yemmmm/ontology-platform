# HTTP API

本文档描述当前运行时实际注册的 HTTP API。完整操作清单由 FastAPI `app.openapi()` 生成；业务
契约、边界和示例由人工维护。

## 地址与认证

- `./scripts/start-local.sh` 与本地 systemd 服务：`http://127.0.0.1:8001/api`
- 手动运行 `uv run uvicorn app.main:app --reload`：默认 `http://127.0.0.1:8000/api`
- OpenAPI UI：对应 backend 地址的 `/docs`

只有三个 `/api/health*` endpoint 和 `POST /api/auth/login` 公开。其他 API、OpenAPI JSON 和 docs
要求 `Authorization: Bearer <API key>` 或有效 UI session。API key 只有创建响应展示一次明文，之后
只能查询 metadata 或幂等撤销。

- `read`：读取、export、Context Query 与 scoped SPARQL。
- `model`：包含 read，并允许建模、Build Session 与受治理 RDF 写入。
- `admin`：包含 model/read，并允许 Project、Ontology、API key 与全局治理操作。

Project-bound 主体只能访问其 Project；显式提交 foreign Project 返回 `403 forbidden_scope`，只提供
foreign opaque resource ID 时返回 404。UI session 写请求还要求可信 Origin、CSRF cookie 与
`X-CSRF-Token` 相等。

### R4.0-006 主体与角色授权

普通用户仅通过个人 Key 访问；管理员仍可登录。`users.is_org_admin`／停用状态由服务端检查，
普通用户（包括旧 session）不能登录或取得组织管理员权限。Key scope 和语义 Grant 分别判断。

Org Admin 用 `POST /api/users` 登记普通用户（`username`），`GET /api/users`／`/{user_id}`
读取，`PATCH /api/users/{user_id}` 修改 `username` 或 `disabled`；不接受密码、管理员标志或自助注册。
Org Admin 用 `POST /api/projects/{project_id}/members`（`user_id`）添加成员，
`DELETE .../members/{user_id}` 移除；Project Admin 只能读取本项目成员的最小身份。

本项目 Admin 可管理 `/api/projects/{project_id}/semantic-access-roles`：
GET／POST 及 `/{role_id}` 的 GET／PATCH／DELETE。创建字段为 `name`、`description`、`grants`，
以及可选的 `business_role_iri`＋`business_role_ontology_id`。名称项目内唯一，重复返回 409；
Grant 复用保护集的精确字符串规范（至多 64 个、单个至多 128 字符、非空可打印、去重），不按空白或
大小写自动归并。显式关联核对同项目已有 `semantic_definition.semantic_role=business_role`，
读回 `business_role_status` 为 `unassociated`／`valid`／`missing`／`invalid_definition`；
业务角色后续变更／缺失不改变权限，可由管理员修正关联。

`GET /api/projects/{project_id}/members/{user_id}/roles` 读取角色 id 集合；PUT 使用
`{"role_ids": ["role-id"]}` 原子替换（空列表移除全部角色）。跨项目或不存在的角色使整个请求
返回 422，原集合不变。read／model Key 不能调用上述管理接口；Project Admin 不读取全局用户。

`POST /api/api-keys` 必须提交 `user_id`、`name`、`project_id` 和 `scopes`；项目 Key 的用户
必须已经加入本项目，组织 admin Key 必须归属启用的组织管理员。明文仍仅创建时返回。
读回包含 `user_id`，不含 Grant。PATCH 仅可修改 `name`，不能转移用户／项目或提高 scope。
旧 `semantic_grants` 字段在创建／更新时均返回 422；旧 Key Grant 不迁移或参与授权。
仅既有服务端 bootstrap 登记路径允许无归属组织 admin 凭据，API 省略用户或使用 bootstrap 名称
均不能取得该例外。已有无归属普通 Key 需由管理员明确配置成员并重新发行，不自动猜测归属。
R4.0-007 已将 Team 的宿主临时 admin、Protocol model 和 Modeling read Key 显式绑定
到既有 operator-admin 所属用户。仅在本轮新建或宿主确认成功 fork 的新 Project 中加入
该用户成员；existing／普通 checkpoint 接续不修改成员权限，缺成员时返回可定位错误。
不创建用户或语义角色，不复制旧 Project 的权限。

每次 HTTP 请求／MCP 调用重新检查 Key、所属用户、项目成员和角色。有效 Grant 为角色并集；
同用户同项目的所有 Key 共用角色权限，各 Key scope／撤销独立。组织 Key 也先检查所属用户
启用且仍为组织管理员，再进入管理员绕过；用户管理员标志不能提升项目 read Key 的 scope。
正常无角色／空 Grant 仍可读普通资源；依赖故障／损坏角色配置返回可重试 `503 dependency_error`
（MCP 为同名错误），不当作正常空权限或永久撤销凭据。

管理提交后的新调用无需重启即可生效。有效 scope／Grant 变化使旧 Context cursor 返回
`context_cursor_mismatch`，从首页重查；等价有效权限不使分页失效，凭据失效先返回认证错误。
移出项目会同事务撤销该用户本项目 Key 并清空分配，重新加入不复活旧 Key；禁用／重启用用户
可失效／恢复仍合格的未撤销 Key。删角色清分配，删项目级联清成员与角色而保留全局用户。
checkpoint fork 保留保护集和业务定义，成员、Key、权限角色与分配不复制。

主体、分配及 Grant 仅存在控制面，不加入 RDF／模型导出／SPARQL／Consumer 语义响应。
受治理读取继续保持无权与不存在不可区分、分页前过滤和保护集 OR；权限角色不会授予外部数据
或业务执行权限，也不会自动检测说明／脚本中复制的敏感文本。

## 当前主要工作流

### Project、Ontology 与需求澄清

- Project/Ontology CRUD 与默认语义工作区：`/api/projects`、
  `/api/projects/{project_id}/ontologies`
- Project Brief、Interview Answer 与 Competency Question：
  `/api/projects/{project_id}/brief`、`/api/projects/{project_id}/interview-answers`、
  `/api/projects/{project_id}/competency-questions`
- 构建上下文：`GET /api/projects/{project_id}/build-context`

创建 Ontology 后，平台会初始化默认 RDF 图和 Graph Set。历史或不完整工作区可使用当前注册的
workspace repair 操作修复。

### 外部 Agent 建模

外部 Agent 使用 Build Session 和 Ontology Lease 管理恢复与并发，再通过 Modeling Batch 完成
`dry_run` 和 apply。平台保存建模结果、幂等状态、冲突和审计，不在 HTTP 层替 Agent 做领域判断。

R1.1 分阶段工作流使用 Build Session 下的 Modeling Workflow Artifact 和 Modeling Execution Event：
Artifact 以 `artifact_key` 创建不可变线性版本，Event 以 `client_event_id` 幂等追加并获得 Session 内
稳定序号。问题事件使用 current-head compare-and-set 保存 `open/answered/skipped/uncertain/reopened`
状态；更正只能追加 superseding event。`GET .../modeling-workflow:export` 提供完整 JSON 或 Markdown
复盘记录，`GET /api/build-sessions/{session_id}` 只内联小型 `modeling_workflow_summary`。

v4 R4.0-012 阶段性停用 Evidence／完整 lineage。Agent 读取业务资料理解与核对语义，
候选、Batch 与 canonical command 不接受追溯专用字段，不要求登记引用或补齐追溯链。
写入回执、审计、授权、图版本和必要恢复继续由平台与宿主保存；独立语义验收仍核对获准资料。
专用证据与追溯入口已撤下，旧参数按现有参数验证错误拒绝；不提供历史只读兼容。

### 查询与验证

- 授权范围发现：`GET /api/semantic/scopes:discover`
- Context Query：`POST /api/semantic/context:query`
- scoped SPARQL：`POST /api/semantic/sparql:query`
- Ontology read model、SHACL validation、reasoning 和 rule
  execution 均以清单中的当前操作为准。

Context Query 返回结构化资源、事实、关系、操作、约束和真实完整性状态，不生成最终自然语言答案。
旧 Agent Test API 已移除；外部 Agent 负责组合结构化结果并生成最终答案。

R1.2-004 起 Context Query 支持一次提交一组同主题的相关表达式。请求体的标准字段是
`queries: list[string]`（1–8 项，每项 trim 后 1–2000 字符、合计 ≤ 8000 字符）；兼容字段
`query: string` 等价于 `queries: [query]` 的单元素列表，二者必须提供且只提供一个。服务对去重
后的规范化表达式只执行一次检索与一次 embedding 批处理；融合结果按证据层级、得分、表达式支持数
和 R1.2-003 既有 tie-breaker 排序，输入顺序不影响打分或排序。匹配结果与相关上下文使用独立预算
（`limit` 默认 20/最大 100；`context_limit` 默认 100/最大 1000）和独立的游标：`match_cursor`
继续下一页匹配，`context_cursor` 只在当前匹配页内继续上下文。请求同时只能携带其中一种 cursor，
且 cursor 必须与当前 principal、Project/Ontology 范围、原始 `queries`、过滤、深度、页大小以及
绑定的 `workspace_version`/source signature 完全匹配；否则返回 `400 invalid_context_cursor`、
`400 context_cursor_mismatch` 或 `409 context_snapshot_changed`。响应新增 `query.queries`、
`query.normalized_queries`、`primary_matches[*].matched_queries`、`primary_matches[*].fusion`、
`related_context[*].root_paths`、`matches_page`、`context_page`，顶层 `truncated` 等于两页
`truncated` 的逻辑或。配置 `SEMANTIC_CONTEXT_QUERY_CURSOR_SIGNING_SECRET` 时 cursor 可跨进程
重启继续验证；未配置时后端使用进程私有随机完整性材料并经能力发现声明该限制。

能力发现：`GET /api/mcp/tools` 在响应的 `capabilities.semantic_context_query` 中返回当前部署
公开的 `queries`/`query`/`limit`/`context_limit`/`depth` 上下限、cursor 种类
（`match`、`context`）、cursor 生命周期（默认 600 秒），以及是否配置了稳定 cursor 签名密钥。
该字段是 R1.2-007 capability discovery 在 Context Query 合约上的唯一展示位置，未引入新路由。

消费 Agent 新会话可先调用范围发现。无筛选时它以稳定游标分页返回当前主体可访问的 Project 与
Ontology；`query` 仅匹配稳定 ID 或名称（trim + case-insensitive contains），`queryable` 仅筛选
Ontology。Project 项返回 `complete/partial/unavailable` 和排除清单，Ontology 项分别返回业务
`status`、技术 `queryable`、不可用原因、当前 `workspace_version` 和简要派生警告。响应中的
`query_scope` 可直接用于 Context Query/scoped SPARQL；实际查询仍会重新校验授权、就绪性和版本。
Cursor 同时绑定筛选条件和当前授权 Project 边界，不能在 Project-bound 与组织管理员主体之间或
不同 Project 主体之间复用。配置 `SECRET_KEY` 时 cursor 可跨进程重启继续验证；未配置时后端使用
进程私有随机完整性材料，cursor 只能在生成它的进程生命周期内使用，重启或切换进程后应重新从
第一页发现。

## 错误和兼容性边界

- FastAPI 参数校验通常返回 `422`；业务冲突和不存在资源按各操作实现返回 `4xx`。
- 缺少/无效/revoked credential 返回 `401 invalid_authentication`；scope 或 Project 越权返回
  `403 forbidden_scope`；领域 payload 命中高可信真实秘密返回 `422 secret_in_payload`。
- 受治理语义编辑、Modeling Batch 和 Build Session 有各自的冲突、幂等及恢复语义；调用方应保留
  返回的 session、lease、batch 和 checkpoint 标识。
- Workflow Artifact/Event 写入要求 `model`，读取/export 要求 `read`；单 Artifact 版本上限 1 MiB、
  Event payload 上限 64 KiB、export 上限 8 MiB。版本过期、foreign 引用、问题 stale head 和幂等
  冲突分别返回稳定业务 code，命中 secret 时不会自动修改或回显内容。
- 当前仍注册的 deprecated 兼容操作会继续出现在下方清单中；未注册的旧 Version、Proposal、
  Catalog、Connector 和 Neo4j Entity 接口不是当前能力。
- R-010 的 Dify 端到端验收套件尚未实现，当前没有可引用的 Dify 基准通过率。

## 完整运行时操作清单

下方区块由脚本维护，不要手工编辑。接口变更后运行：

```bash
cd backend
uv run python ../scripts/sync-interface-docs.py --write
```

<!-- BEGIN GENERATED HTTP API INVENTORY -->

| Tag | Method | Path | Summary |
| --- | --- | --- | --- |
| authentication | `GET` | `/api/api-keys` | List Api Keys |
| authentication | `GET` | `/api/api-keys/{key_id}` | Get Api Key |
| authentication | `GET` | `/api/auth/me` | Me |
| authentication | `POST` | `/api/api-keys` | Create Key |
| authentication | `POST` | `/api/api-keys/{key_id}:revoke` | Revoke Api Key |
| authentication | `POST` | `/api/auth/login` | Login |
| authentication | `POST` | `/api/auth/logout` | Logout |
| authentication | `PATCH` | `/api/api-keys/{key_id}` | Update Api Key |
| build sessions | `GET` | `/api/build-sessions/{session_id}` | Get Build Session |
| build sessions | `GET` | `/api/projects/{project_id}/build-context` | Get Project Build Context |
| build sessions | `POST` | `/api/build-sessions/{session_id}/checkpoints` | Save Build Checkpoint |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire` | Acquire Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:release` | Release Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:renew` | Renew Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}:cancel` | Cancel Build Session |
| build sessions | `POST` | `/api/build-sessions/{session_id}:complete` | Complete Build Session |
| build sessions | `POST` | `/api/build-sessions/{session_id}:resume` | Resume Build Session |
| build sessions | `POST` | `/api/projects/{project_id}/build-sessions` | Create Build Session |
| checkpoint-data | `POST` | `/api/checkpoint-data/capture` | Capture Data |
| checkpoint-data | `POST` | `/api/checkpoint-data/fork` | Fork Data |
| mcp-catalog | `GET` | `/api/mcp/tools` | List Mcp Tools |
| modeling batches | `GET` | `/api/build-sessions/{session_id}/modeling-batches` | List Session Modeling Batches |
| modeling batches | `GET` | `/api/modeling-batches/{batch_id}` | Get Modeling Batch |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/modeling-batches` | List Ontology Modeling Batches |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/modeling-context` | Get Modeling Context |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/semantic-read-models/{model_name}` | Get Ontology Read Model |
| modeling batches | `POST` | `/api/build-sessions/{session_id}/modeling-batches` | Submit Modeling Batch |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-execution-events` | List Modeling Execution Events |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-workflow-artifacts` | List Modeling Workflow Artifacts |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-workflow:export` | Export Modeling Workflow Record |
| modeling workflow | `GET` | `/api/modeling-execution-events/{execution_event_id}` | Get Modeling Execution Event |
| modeling workflow | `GET` | `/api/modeling-workflow-artifacts/{workflow_artifact_id}` | Get Modeling Workflow Artifact |
| modeling workflow | `POST` | `/api/build-sessions/{session_id}/modeling-execution-events` | Record Modeling Execution Event |
| modeling workflow | `POST` | `/api/build-sessions/{session_id}/modeling-workflow-artifacts` | Create Modeling Workflow Artifact |
| ontologies | `GET` | `/api/ontologies/{ontology_id}` | Get Ontology |
| ontologies | `GET` | `/api/ontologies/{ontology_id}/workspace-context` | Get Ontology Workspace Context |
| ontologies | `GET` | `/api/projects` | List Projects |
| ontologies | `GET` | `/api/projects/{project_id}` | Get Project |
| ontologies | `GET` | `/api/projects/{project_id}/ontologies` | List Ontologies |
| ontologies | `POST` | `/api/ontologies/{ontology_id}/workspace/repair` | Repair Ontology Workspace |
| ontologies | `POST` | `/api/projects` | Create Project |
| ontologies | `POST` | `/api/projects/{project_id}/ontologies` | Create Ontology |
| ontologies | `POST` | `/api/projects/{project_id}/ontology-workspaces/repair` | Repair Project Ontology Workspaces |
| ontologies | `PATCH` | `/api/ontologies/{ontology_id}` | Update Ontology |
| ontologies | `PATCH` | `/api/projects/{project_id}` | Update Project |
| ontologies | `DELETE` | `/api/ontologies/{ontology_id}` | Delete Ontology |
| ontologies | `DELETE` | `/api/projects/{project_id}` | Delete Project |
| project interview | `GET` | `/api/ontologies/{ontology_id}/build-overview` | Get Build Overview |
| project interview | `GET` | `/api/projects/{project_id}/brief` | Get Project Brief |
| project interview | `GET` | `/api/projects/{project_id}/competency-questions` | List Competency Questions |
| project interview | `POST` | `/api/competency-questions/{question_id}/status` | Set Competency Question Status |
| project interview | `POST` | `/api/competency-questions/{question_id}/validate` | Validate Competency Question |
| project interview | `POST` | `/api/projects/{project_id}/competency-questions` | Create Competency Question |
| project interview | `POST` | `/api/projects/{project_id}/interview-answers` | Create Interview Answer |
| project interview | `PATCH` | `/api/competency-questions/{question_id}` | Update Competency Question |
| project interview | `PATCH` | `/api/projects/{project_id}/brief` | Update Project Brief |
| semantic | `GET` | `/api/semantic/canonical-mode` | Get Canonical Mode |
| semantic | `GET` | `/api/semantic/edits/audits` | List Semantic Edit Audits |
| semantic | `GET` | `/api/semantic/export` | Export Dataset |
| semantic | `GET` | `/api/semantic/graph-sets` | List Graph Sets |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}` | Get Graph Set |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}/export` | Export Graph Set |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}/read-models/{model_name}` | Read Model |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}/shapes/classes/{class_iri}` | Read Class Shape Guidance |
| semantic | `GET` | `/api/semantic/graphs` | List Graph Registry |
| semantic | `GET` | `/api/semantic/graphs/{graph_iri}` | Get Graph Registry |
| semantic | `GET` | `/api/semantic/migrations` | List Migration Runs |
| semantic | `GET` | `/api/semantic/migrations/{run_id}` | Get Migration Run |
| semantic | `GET` | `/api/semantic/projection-jobs` | List Projection Jobs |
| semantic | `GET` | `/api/semantic/projection-jobs/{job_id}` | Get Projection Job |
| semantic | `GET` | `/api/semantic/projections/status` | Projection Status |
| semantic | `GET` | `/api/semantic/reasoning-runs` | List Reasoning Runs |
| semantic | `GET` | `/api/semantic/reasoning-runs/{run_id}` | Get Reasoning Run |
| semantic | `GET` | `/api/semantic/resources/{resource_iri}` | Read Resource |
| semantic | `GET` | `/api/semantic/rule-definitions` | List Rule Definitions |
| semantic | `GET` | `/api/semantic/rule-definitions/{rule_id}` | Get Rule Definition |
| semantic | `GET` | `/api/semantic/rule-runs` | List Rule Runs |
| semantic | `GET` | `/api/semantic/rule-runs/{run_id}` | Get Rule Run |
| semantic | `GET` | `/api/semantic/scopes:discover` | Discover Semantic Scopes |
| semantic | `GET` | `/api/semantic/statements` | List Statements |
| semantic | `GET` | `/api/semantic/status` | Get Governance Status |
| semantic | `GET` | `/api/semantic/validation-runs` | List Validation Runs |
| semantic | `GET` | `/api/semantic/validation-runs/{run_id}` | Get Validation Run |
| semantic | `POST` | `/api/semantic/canonical-writes:compile-and-apply` | Compile And Apply Product Command |
| semantic | `POST` | `/api/semantic/context:query` | Query Semantic Context |
| semantic | `POST` | `/api/semantic/datasets:load` | Load Dataset |
| semantic | `POST` | `/api/semantic/derived-results:gc` | Run Derived Results Gc |
| semantic | `POST` | `/api/semantic/derived-results:reconcile` | Reconcile Derived Results |
| semantic | `POST` | `/api/semantic/edits` | Create Semantic Edit |
| semantic | `POST` | `/api/semantic/graph-sets` | Create Graph Set |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/construct-runs` | Create Graph Set Construct Run |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/projection-jobs` | Create Projection Job For Set |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/reasoning-runs` | Create Graph Set Reasoning Run |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/rule-runs` | Create Graph Set Rule Run |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/validation-runs` | Create Graph Set Validation Run |
| semantic | `POST` | `/api/semantic/graphs` | Register Graph |
| semantic | `POST` | `/api/semantic/migrations` | Create Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:cutover` | Cutover Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:parity-check` | Run Migration Parity Check |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:rerun-failed-batches` | Rerun Failed Migration Batches |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:rollback` | Rollback Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:run-next-batch` | Run Next Migration Batch |
| semantic | `POST` | `/api/semantic/migrations:preflight` | Preflight Migration |
| semantic | `POST` | `/api/semantic/ontologies/{ontology_id}/retrieval:rebuild` | Rebuild Ontology Retrieval |
| semantic | `POST` | `/api/semantic/projection-jobs/{job_id}:run` | Run Projection Job |
| semantic | `POST` | `/api/semantic/projections:reconcile` | Reconcile Projections |
| semantic | `POST` | `/api/semantic/reasoning-runs` | Create Reasoning Run |
| semantic | `POST` | `/api/semantic/rule-definitions` | Create Rule Definition |
| semantic | `POST` | `/api/semantic/sparql:query` | Query Sparql |
| semantic | `POST` | `/api/semantic/validation-runs` | Create Validation Run |
| semantic | `PUT` | `/api/semantic/graph-sets/{graph_set_id}/members` | Update Graph Set Members |
| semantic | `PATCH` | `/api/semantic/graphs/{graph_iri}/editability` | Update Graph Editability |
| semantic | `PATCH` | `/api/semantic/rule-definitions/{rule_id}` | Update Rule Definition |
| semantic | `DELETE` | `/api/semantic/rule-definitions/{rule_id}` | Delete Rule Definition |
| semantic-protection-sets | `GET` | `/api/projects/{project_id}/protection-sets` | List Protection Sets |
| semantic-protection-sets | `GET` | `/api/protection-sets/{protection_set_id}` | Get Protection Set |
| semantic-protection-sets | `POST` | `/api/projects/{project_id}/protection-sets` | Create Protection Set |
| semantic-protection-sets | `POST` | `/api/protection-sets/{protection_set_id}/members` | Add Protection Set Members |
| semantic-protection-sets | `PATCH` | `/api/protection-sets/{protection_set_id}` | Update Protection Set |
| semantic-protection-sets | `DELETE` | `/api/protection-sets/{protection_set_id}` | Delete Protection Set |
| semantic-protection-sets | `DELETE` | `/api/protection-sets/{protection_set_id}/members` | Remove Protection Set Members |
| subject semantic access | `GET` | `/api/projects/{project_id}/members` | List Members |
| subject semantic access | `GET` | `/api/projects/{project_id}/members/{user_id}/roles` | Get Member Roles |
| subject semantic access | `GET` | `/api/projects/{project_id}/semantic-access-roles` | List Roles |
| subject semantic access | `GET` | `/api/projects/{project_id}/semantic-access-roles/{role_id}` | Get Role |
| subject semantic access | `GET` | `/api/users` | List Users |
| subject semantic access | `GET` | `/api/users/{user_id}` | Get User |
| subject semantic access | `POST` | `/api/projects/{project_id}/members` | Add Member |
| subject semantic access | `POST` | `/api/projects/{project_id}/semantic-access-roles` | Create Role |
| subject semantic access | `POST` | `/api/users` | Create User |
| subject semantic access | `PUT` | `/api/projects/{project_id}/members/{user_id}/roles` | Put Member Roles |
| subject semantic access | `PATCH` | `/api/projects/{project_id}/semantic-access-roles/{role_id}` | Update Role |
| subject semantic access | `PATCH` | `/api/users/{user_id}` | Update User |
| subject semantic access | `DELETE` | `/api/projects/{project_id}/members/{user_id}` | Delete Member |
| subject semantic access | `DELETE` | `/api/projects/{project_id}/semantic-access-roles/{role_id}` | Delete Role |
| untagged | `GET` | `/api/health` | Health |
| untagged | `GET` | `/api/health/dependencies` | Dependency Health |
| untagged | `GET` | `/api/health/postgres` | Postgres Health |

<!-- END GENERATED HTTP API INVENTORY -->

### R4.0-002 共同业务语义说明

`create/update_class`、`create/update_property`、`create/update_relation_type` 与
`create/update_entity` 的 Modeling Batch payload 支持可选 `semantic_definition`：

```json
{
  "semantic_role": "business_role",
  "business_meaning": "负责审核业务内容",
  "applicability": "售后场景",
  "unknowns": ["审核时限待确认"],
  "not_applicable": ["制造审批"],
  "conflicting_meanings": ["两种审核时限口径待确认"]
}
```

三个文本字段为非空字符串，三个集合字段为非空字符串数组；字段可省略，未知字段及错误类型
返回可修正的合同错误。更新时省略表示保持，`null` 清除整份声明，对象替换整份声明。
RDF 使用资源本身的 `op:semanticDefinition` JSON 字面量；这不会改变正式 Class、平台
resource kind 或权限。角色是已确认业务含义的开放字符串，不按视角推导，也不授予权限。

既有 `class-detail`、`entity-detail`、`ontology-schema-summary`、`property-list`、
`relation-type-list`、`entity-list` 读模型在 `detail_fields.semantic_definition` 返回声明，
对应投影版本为 `semantic-read-v2`。精确 `GET /api/semantic/resources/{resource_iri}` 在
`properties.semantic_definition` 返回声明，并支持上述实体、Class 与 Property 资源。
所有路径保留既有 scope 与 access_view；隐藏资源与不存在资源均返回同形 404／空结果。

局部职责或关系用独立的普通语义节点表达，节点说明本地含义并通过通用关系明确连接上下文、
共享定义、关系定义及两端；从既有关系／statement 读取取得这些引用。节点中的未知、冲突和
不适用保持独立；未返回声明或关系不足以推断不存在约束。业务行继续留在外部系统。

中立候选在 `semantic.semantic_definition` 表达上述声明，unified graph 候选使用可选的
item 字段 `semantic_definition`，Protocol 将已批准内容原样转入 payload。Class 可省略，
`semantic.classes` 是中立 Class ID 列表；普通分组使用关系。候选关系端点可用
`{"definition_ref": "candidate-item-id"}` 引用本候选中的 Class／predicate／entity，
Protocol 绑定平台身份，Modeling 不猜测平台 IRI；已存在资源继续遵循原 receipt 绑定合同。
详见 [当前候选合同](../../modeling_team/references/platform-neutral-candidate-authoring.json)。
本增量不引入 Evidence／lineage、自动同义合并或跨 Project 共享。

### R4.0-003 可复用 Action 与业务参数

Action 和业务参数复用普通 Entity 的稳定身份及 `semantic_definition`，不新增资源类型、
表或路由。Action 声明 `semantic_role: "behavior"`，名称、含义和范围随定义保存；人工或
尚无外部能力的动作合法，无需正式 Class、工具绑定、风险、幂等性或凭证说明。
`create_entity`／`update_entity` 的 Batch 和 canonical payload 新增两个可选注释：

```json
{
  "action_definition": {"input_status": "defined", "output_status": "none"},
  "parameter_definition": {
    "direction": "output",
    "value_kind": "object_reference",
    "cardinality": "single",
    "required": null,
    "occurrence_condition": "成功完成时",
    "result_kind": "updated_input"
  }
}
```

上例展示字段合同；实际 Action 和每个参数分别存于自己的 Entity 上，通过普通关系连接，
不会把它们合并成一个身份。每份注释是非空对象，所有字段可省略；省略表示没有提供说明，
不推导默认值。更新省略整份注释表示保持，`null` 清除整份，对象替换整份。
不支持的字段、值或资源类型返回可修正的 payload 错误。

| 注释字段 | 接受值及含义 |
| --- | --- |
| Action `input_status`／`output_status` | `defined`：已定义并通过关系连接参数；`none`：明确无业务输入／返回值；`unknown`：尚未确认。未声明输出与明确无输出不同 |
| 参数 `direction` | `input`／`output`／`unknown` |
| 参数 `value_kind` | `object_reference`／`value`／`unknown`；对象、属性或共享定义的具体引用在图关系中 |
| 参数 `value_type` | 已确认的非空值类型字符串或 `null`（未知），不从名称猜测 |
| 参数 `required` | 布尔值或 `null`（未知）；结果出现条件也可用 `occurrence_condition` 说明 |
| 参数 `cardinality` | `single`／`collection`／`unknown` |
| 参数 `occurrence_condition`／`unit`／`missing_meaning` | 非空已确认说明或 `null`（未知） |
| 参数 `enum_values` | JSON 标量数组；`[]` 明确没有声明枚举限制，`null` 未确认；省略为没有说明 |
| 参数 `result_kind` | `updated_input`／`new_object`／`computed_value`／`unknown`；更新输入时用普通关系引用具体输入参数 |

已确认参数至少说明名称、业务含义、方向、对象引用或值类型、必填性或结果出现条件以及
单值／集合含义；未确认部分显式保留未知。两个同类输入也保持不同参数身份，身份本身不
证明两个运行时对象不同。本合同不保存实际参数值、业务行或流程调用变量。

条件、效果、局部职责和能力关联使用普通语义节点，分别保留自然语言含义、适用范围、未知
及已知冲突。普通关系将节点连接到动作、适用对象／Class、参数、属性、共享规则或角色。
正式子类适用可由 Class 层次辨明；共同条件和局部追加条件同时保留，明确例外不自动覆盖。
效果的范围说明成功、失败或部分结果条件；定义写入不产生已发生的业务事实或权限。

能力关联节点说明对应含义及范围，并通过普通关系指向独立 Operation。允许零或多个能力，
同一能力可被多个动作引用；不自动推断等价、顺序、完整实现或版本兼容。组合步骤的缺口、
未确认对应和冲突随关联读回。更改关联不改写 Action；真正改变参数、条件或效果时须修改
业务定义。Operation 原有活动工具绑定、正式目标 Class 等校验继续生效。

中立候选在 `semantic.action_definition`／`semantic.parameter_definition` 表达注释；
unified 候选接纳同名可选 item 字段，由 Protocol 将获准内容原样映射到 Entity 命令。
新增中立 `operation` item：`semantic.operation_id` 是独立能力身份，`target_class` 指定
候选内的正式 Class，其余字段沿用 Operation v1。Protocol 翻译为 `create_operation`，
在 Class／Property 后、关联前写入；`definition_ref` 可引用该 Operation 的 item ID。
既有资源继续使用其原有获准读取／receipt 绑定，不能伪造新身份代替绑定。

RDF 在各 Entity 上保存 `op:actionDefinition`／`op:parameterDefinition` JSON 字面量。
`entity-list`／`entity-detail` 在 `detail_fields`、精确资源读取在 `properties` 返回对应对象。
引用保留为普通 RDF 关系；通过 `/api/semantic/statements`（`statement-list`）读取涉及
Class／Operation 的关系，不要求两端是 NamedIndividual。Class 层次从 `class-topology`
等既有入口读取；Operation 自身说明保持在既有受治理能力检索路径中。
`entity-relations` 的两端仍限于 NamedIndividual。

所有读取沿用已有 access_view：隐藏参数、规则或 Operation 的关系引用在计数、排序、
分页前过滤，精确隐藏与不存在响应同形。未返回获准关系不能推断没有约束或实现；IRI
过滤不自动保护复制到可见正文中的敏感文本。本增量不增加 Evidence／lineage、条件判定、
能力选择、外部调用或流程编排。详细中立表达见[候选合同](../../modeling_team/references/platform-neutral-candidate-authoring.json)。

### R4.0-005 业务规则与脚本声明

规则仍为普通 Entity，使用 `semantic_definition.semantic_role: "rule"` 保存名称、业务含义、
适用范围、未知和 `conflicting_meanings`。`create_entity`／`update_entity` 的可选
`rule_definition` 保存业务规则合同，不是 `semantic_rule_definition`／Rule Run 的执行正文：

```json
{
  "rule_definition": {
    "kind": "judgment_constraint",
    "script_language": "Python",
    "script_version": "3.11",
    "script_source": "amount >= 100000",
    "execution_environment": "外部 Consumer 按普通输入关系绑定 amount，输出资格判断；失败返回 error；不允许副作用",
    "input_status": "defined",
    "output_status": "defined",
    "missing_policy": "unknown 保持未知；not_applicable 不适用；empty 是已知空；rejected/error 不产生成功结果",
    "change_note": "脚本、说明、输入输出与范围共同修订；阈值边界冲突保留并交业务复核"
  }
}
```

`kind` 仅允许 `judgment_constraint`／`derivation`；输入／输出状态仅允许
`defined`／`none`／`unknown`。其余六个字段为非空文本或 `null`（未知）。注解是非空对象或
`null`：创建省略不产生声明；更新对象完整替换、`null` 清除、省略保持。各字段可省略，
表示没有信息；部分声明允许保存，不证明规则完整或可执行。已确认规则应按业务资料补齐逐条
语言、版本、正文、执行环境及输入绑定、输出形式、失败／副作用约定。语言不限定为 Python。
未知字段、非法对象／字段类型／枚举值返回可定位到 item 和字段的可修复 payload 错误。

输入／输出使用现有独立参数 Entity 及原 `parameter_definition`，结果含义使用输出的
`semantic_definition`；005 不扩展参数字段。规则与对象、Action、流程、参数、条件、结果
通过普通关系连接。来源沿用 004 的 `sourceKind` 五类值及 `toParameter`、`fromValue`、
`refersToDefinition` 等模型声明关系，保留对象方向、调用／输出参数和迭代作用域，
不将端点身份藏在 JSON 或文本路径中。关系读取使用既有受治理 statements／relations。

中立候选的 `semantic.rule_definition` 由 Protocol 复制到实体创建 payload；unified 候选
接纳同名可选 item 字段，创建／更新复用原批准物化计划及授权身份绑定，不增加中立更新语法。
Batch `_compile`／`prepare` 校验后写入 `op:ruleDefinition` JSON 字面量。
`entity-list`／`entity-detail` 返回 `detail_fields.rule_definition`；精确 resource 读取返回
`properties.rule_definition`。授权过滤仍先于分页／计数／排序，隐藏与不存在精确读取同形。

平台只保存和读取脚本，不求值、不调用外部能力、不自动生成派生关系／节点；显式受治理
建模仍可提交已确认定义。Shape、OWL、平台 `rule-result` 和外部业务判断保持原边界。
脚本、说明、合同和范围共同维护，已知冲突和共同变更说明保留；平台不自动判断自由文本冲突
或敏感信息，IRI 过滤不保护复制出的正文。未返回关系不能解释为无输入或无约束。
不新增表、规则专用资源／路由、执行器或 Evidence／lineage。完整合同见
[规则声明](../../modeling_team/references/platform-neutral-candidate-authoring.json)的 `business_rule_semantics`。
