# R-008 API/MCP 认证、授权与项目隔离设计

## 1. 状态与决策摘要

实现状态：`已实现`。本设计细化 `docs/requirements-v1.0.md` 的 R-008，功能契约已由用户逐项确认。

1. API key 与 UI session 都解析为服务器创建的 `AuthPrincipal`，业务 payload 不能创建或覆盖主体。
2. `read < model < admin` 是包含关系；每张 key 可绑定一个 Project，只有未绑定 Project 的
   `admin` 是全组织 admin。
3. 全组织 admin 管理 Project 和全组织 key；Project-bound admin 只管理本 Project 的 Ontology
   与 key。
4. API key 明文只在创建时返回，之后不可修改、不可重显、只能幂等撤销。
5. Project/Ontology/Graph Set/Evidence/Build Session/Modeling Batch/查询范围都解析回 Project 后授权；
   无法证明归属的 legacy/ad-hoc 资源对 Project-bound 主体 fail closed。
6. 允许保存凭证术语、凭证需求和脱敏占位符，只拒绝高可信真实秘密值；秘密不进入错误、日志、
   Batch、Audit 或 RDF。
7. 新增最小、只追加的安全事件记录；不在 R-008 建全量请求/查询审计或导出能力。

## 2. 目标与非目标

### 2.1 目标

- 为 HTTP、MCP 和浏览器 UI 建立不可伪造的认证主体。
- 在所有现有 API/MCP 能力上执行统一 scope 和 Project 归属校验。
- 保持 R-006 scoped SPARQL 的服务器端 dataset 强约束，阻断 `GRAPH ?g` 跨项目读取。
- 将所有写入 actor 强制设为认证主体，并记录主体伪造、认证失败和授权失败事件。
- 提供最小 API key 生命周期与 bootstrap 路径，使本地、CI 和外部 Agent 可实际接入。
- 对领域内容执行统一高可信秘密扫描和日志脱敏。

### 2.2 非目标

- 多用户/服务账号管理 UI、SSO、MFA、密码找回或细粒度 Ontology/Graph Set 角色。
- API key 更新、明文重显、恢复撤销、轮换 UI 或自动轮换。
- 多组织、租户、计费、配额或跨组织共享。
- 全量成功请求审计、查询文本审计、审计导出或保留策略。
- 跨域 UI 部署。v1 浏览器调用使用当前 Vite/反向代理提供的同源 `/api` 路径。

## 3. 身份模型与持久化

### 3.1 AuthPrincipal

HTTP 与 MCP adapter 只向服务传入以下不可由业务 payload 伪造的上下文：

```text
AuthPrincipal
  subject_type: api_key | user
  subject_id: API key ID | User ID
  actor: key:<key_name> | user:<username>
  scopes: read/model/admin 的规范集合
  project_id: Project ID | null
```

- `admin` 隐含 `model` 和 `read`，`model` 隐含 `read`；存储可保留调用方选择的合法集合，授权时使用
  展开后的 effective scopes。
- `project_id=null` 只有 `admin` 主体合法；`read/model` key 必须绑定 Project。
- UI bootstrap user 固定解析为全组织 admin，不把用户名或权限放在可修改请求字段中。
- 同一 HTTP 请求同时携带 Bearer key 与 session cookie 时，若主体不同则返回 401 并记录安全事件，
  不静默选择其中一个。

### 3.2 数据模型

复用 `api_keys` 并新增：

- `users`：`id`、唯一 `username`、Argon2id `password_hash`、`session_version`、时间字段。首版只有
  bootstrap admin。
- `security_audit_events`：`id`、`event_type`、`outcome`、`actor`、`auth_method`、字符串型
  `project_id`、可选 `resource_type/resource_id`、已脱敏 `details`、`created_at`。

`security_audit_events.project_id` 不设外键，确保 Project 删除后事件仍保留。事件表只追加，产品 API
不提供更新/删除/导出。`details` 使用字段 allowlist，禁止写入 payload、Authorization、cookie、密码、
API key、CSRF token、命中的秘密值或原始 SPARQL。

`api_keys` 现有 Project 外键继续存在。直接 API 不提供硬删除；删除 Project 时在同一受控流程中先把
仍有效 key 标记为 revoked 并记录事件，再删除 Project，key 行可随 Project 级清理移除，事件保留。

### 3.3 密码、key 与 session

- bootstrap 密码使用 Argon2id 和每密码独立 salt；不得用 SHA-256 存密码。实现使用成熟 Argon2
  library，并把参数封装在一个 password service，便于未来升级 hash。
- API key 使用 `secrets` 生成 32 位 base62 随机体，格式为 `sk_<highest-scope>_<random>`；服务端只存
  SHA-256 哈希。高熵 key 适合快速哈希反查，数据库不得保存明文或可逆加密值。
- 创建 key 返回一次 `plaintext_key`；list/get 永不返回 hash 或明文。key 的 Project/scopes 创建后
  不可更新；`:revoke` 幂等设置 `revoked_at`，重复撤销返回当前 metadata。
- UI session 使用 Starlette 签名 cookie，内容只有 user ID、username、session version 和过期时间，
  不含密码、key 或 CSRF secret。cookie 为 HttpOnly、SameSite=Lax、7 天；生产环境设置 Secure。
- `SECRET_KEY` 已配置时跨重启保持 session；未配置时进程生成一次随机 key 并 warning，服务仍可拉起，
  但重启会使旧 session 失效。任何环境都没有 `AUTH_DISABLED`。
- logout 清除 session 与 CSRF cookie。首版无服务端 session 表，已复制的 cookie 在签名 key、
  `session_version` 或 7 天到期前无法逐个撤销；修改 bootstrap 密码时递增 session version，作为全量
  session 失效接缝。首版不提供密码修改 UI。

## 4. Bootstrap 与认证协议

### 4.1 Bootstrap

应用启动时在 migration 已执行的数据库上运行幂等 bootstrap：

- `ONTOLOGY_BOOTSTRAP_ADMIN_USER` 与 `_PASSWORD` 都设置且用户不存在：创建 admin user。
- 两者都未设置：warning，不阻断服务；已有 API key/session 仍可用。
- 只设置其中一项：配置错误并拒绝启动，避免产生不可登录的半配置身份。
- `ONTOLOGY_BOOTSTRAP_ADMIN_API_KEY` 设置：校验其为完整全组织 admin key，按 hash 幂等创建固定名称
  的 bootstrap key。相同 hash 已存在则复用；同名但不同 key 不覆盖，记录 warning 并要求显式撤销/
  新建，避免以环境变量暗中轮换不可变 key。

测试 fixture 创建真实 admin key hash并给 TestClient 设置 Bearer header；不得通过配置或 dependency
提供匿名旁路。

### 4.2 HTTP

- 公开：三个 `/api/health*` 和 `POST /api/auth/login`。
- 受保护：其他 API、OpenAPI JSON 和交互文档。缺少、无效或 revoked credential 返回统一 401，带
  `WWW-Authenticate: Bearer`，响应不泄漏 key/user 是否存在。
- login 使用统一失败响应；成功后设置 session/CSRF cookie并记录事件。`GET /api/auth/me` 返回主体
  和权限；`POST /api/auth/logout` 清理 cookie。
- 同源 UI 的非安全方法请求若使用 session，必须同时携带 double-submit CSRF cookie 和
  `X-CSRF-Token`。浏览器 `Origin` 必须精确命中 `ONTOLOGY_UI_ORIGINS` 显式 allowlist；不得直接与
  后端看到的 Host 比较，因为当前 Vite proxy 的 `changeOrigin=true` 会重写 Host。allowlist 禁止
  `*`，开发默认仅允许 `http://127.0.0.1:5173` 与 `http://localhost:5173`，生产必须显式配置 HTTPS
  origin。Bearer 请求不需要 CSRF，也不信任 forwarded host/proto 来扩大 allowlist。
- 前端先调用 `/auth/me`；401 显示登录页。`apiRequest` 对 cookie 请求使用同源 credentials，为写请求
  添加 CSRF header；运行期 401 清空 UI 主体并回到登录页。

### 4.3 MCP

- `AuthenticatedFastMCP.run()` 在进入任何 stdio/SSE/streamable-http event loop 前读取
  `ONTOLOGY_MCP_API_KEY`，打开数据库会话并解析主体。缺少、无效或 revoked key 时抛出无秘密的启动
  错误，进程非零退出。
- 覆写 `run()` 而不是只在 `if __name__ == "__main__"` 中检查，避免其他调用方直接执行
  `mcp.run()` 绕过。模块导入和 runtime registry 枚举不触发认证，保持文档/测试检查可用。
- 成功主体缓存在 MCP runtime，只读使用；每次 tool call 仍从数据库重新确认 key 未撤销，确保运行中
  撤销无需重启即可生效。
- 所有工具通过统一 `_run_tool` 授权包装器执行，传入 required scope 和 Project resolver。工具 payload
  中的 actor 仅用于检测伪造，不能覆盖 runtime principal。

## 5. 授权与 Project 解析

### 5.1 Scope 分类

- `read`：GET/list/get/export、Context Query、read-only SPARQL、Evidence 查询和 MCP health。
- `model`：`read` 加 Brief/Question 修改、Build Session/Checkpoint/Lease、Evidence 创建/关联、
  Modeling Batch submit/apply、受治理 RDF 编辑、Graph Set 成员/规则/推理/投影等 Ontology 内容写入。
- `admin`：`model` 加 Project/Ontology/key 管理、workspace repair、migration、canonical mode 切换、
  derived GC 和其他跨本体治理操作。

每个 FastAPI operation 和 FastMCP tool 都必须出现在一份显式 policy registry 中。自动化测试枚举
FastAPI routes 和 MCP runtime registry：除明确公开 HTTP route 外，缺少 scope 分类即失败，防止未来
新增接口默认匿名或默认最低权限。

### 5.2 管理边界

- 全组织 admin：列出/创建/读取/更新/删除全部 Project；管理任意 Project-bound key 和全组织 key；
  管理任意 Ontology。
- Project-bound admin：`GET /projects` 只返回自身 Project；可读取自身 Project metadata，不能创建、
  更新或删除 Project；可管理本 Project Ontology 和本 Project key；不能创建/查看/撤销其他 Project
  或全组织 key。
- Project-bound read/model：只能读取自身 Project metadata 和授权范围；不获得 Ontology/key 管理权。
- 创建 key 时，调用者不能授予超过自身 effective scopes 的权限。Project-bound admin 创建的 key
  必须绑定同一 Project；只有全组织 admin 可创建 `project_id=null` key。

### 5.3 资源归属解析

授权服务按稳定链路解析目标 Project：

```text
Project -> project_id
Ontology -> ontology.project_id
Build Session -> session.project_id
Modeling Batch -> batch.build_session.project_id
Evidence Artifact/Reference/Association -> row.project_id
Graph Set -> ontology scope_id -> ontology.project_id
Named Graph -> Graph Registry / Ontology workspace -> ontology.project_id
Rule Definition -> semantic_rule_id -> SemanticRuleModel.ontology_id -> ontology.project_id
Context Query/SPARQL -> request project_id + every ontology.project_id
```

- 路径、query、body 中出现多个 Project 线索时必须全部一致；任一不一致返回
  `403 forbidden_scope` 并记录事件。
- 明确提交 foreign `project_id` 返回 403。只给出 foreign opaque resource ID 时返回 404，避免确认其他
  Project 资源是否存在；两者都不得返回数据片段。
- Project-bound 主体访问无法唯一解析到 Project 的 legacy/ad-hoc Graph Set、graph IRI、migration
  scope 或 dataset load 时拒绝；只有全组织 admin 可操作明确列入 admin policy 的全局治理能力。
- 新建 Rule Definition 必须显式提交 `ontology_id`，服务同时创建/更新同 Ontology 的
  `SemanticRuleModel` 与关联 definition；list 对 Project-bound 主体只返回其 Project 的 ontology-bound
  definitions，get/update/delete 通过关联解析归属。`semantic_rule_id=null` 的 legacy definition 只对
  全组织 admin 可见和可管理。Rule/Construct 执行在任何读取/写图前校验 definition 的 Ontology 与
  目标 Graph Set scope_id 完全一致；Project-bound 主体不能执行 legacy definition。
- 服务层的授权接缝是最终门槛，REST/MCP adapter 的预检查不能替代它；避免另一个 adapter 绕过。

## 6. Actor、审计与错误

- 所有领域写操作只使用 `principal.actor`。现有 `actor` 请求字段暂时保留兼容，但仅用于比较；缺省无
  warning，不一致则领域操作仍以认证主体执行，并新增 `actor_spoof_attempt` 安全事件。
- 若目标模型有 `warning_state`（如 Semantic Edit Audit），同时写入不含自报 actor 原文的
  `actor_overridden=true`；没有 warning 字段的写路径只记录安全事件。
- Modeling Batch 的 `ModelingAuthorizationContext`、R-005 authorize_read 接缝和其他已有授权上下文
  改为携带同一个 principal，不再使用 `system:unattributed`。
- 401、403、actor spoof、login、key create/revoke 事件写入独立事务；授权失败事件不能因业务事务回滚
  丢失。若安全事件数据库写入本身失败，认证/授权继续 fail closed，并输出不含 credential 的错误日志。

稳定错误码：

| HTTP | code | 语义 |
| --- | --- | --- |
| 401 | `invalid_authentication` | 缺少/无效/revoked key 或无效 session |
| 403 | `forbidden_scope` | scope、Project 或管理边界不允许 |
| 404 | 既有 not-found code | opaque foreign resource，防枚举 |
| 422 | `secret_in_payload` | 领域内容含高可信真实秘密值 |
| 429 | `login_rate_limited` | 同主体短时间连续失败的最小进程内保护 |

login 对不存在用户和密码错误返回相同 401。首版使用小型进程内失败窗口抑制暴力尝试，不建分布式
限流；完整容量/分布式治理属于 R-204。

## 7. 统一秘密扫描与日志脱敏

### 7.1 扫描边界

扫描器递归处理领域写入的字符串、dict/list、RDF/SPARQL 文本和将写入 audit delta 的规范化结构，
必须在任何 Postgres/RDF/Batch/Audit 持久化之前执行。覆盖 Semantic Edit、Modeling Batch、Evidence
Artifact/Reference、Brief/Question、Fact Evidence、规则/操作语义和其他领域文本写路径。

认证传输字段（login password、Bearer header、创建 API key 的一次性明文）不作为领域 payload
扫描，否则认证本身无法工作；它们走专用认证代码且永不进入普通日志或 domain audit。

### 7.2 高可信与允许值

拒绝完整平台 key、完整 JWT 三段 token、AWS access key、包含非占位 token 的 Bearer 值和已有
Operation secret 实例字段。允许：

- `api_key`、`password`、`Authorization`、`credential` 等术语和 predicate/字段名；
- Operation `credential_requirements.reference_type=api_key` 等凭证需求类型；
- `<TOKEN>`、`${API_KEY}`、`REDACTED`、`***`、`your-token`、明显 `x...x` 等脱敏占位符。

匹配错误只返回 pattern category，不返回值、path 中的敏感内容或周边文本。扫描器用固定、有界正则，
输入长度沿用现有请求上限，避免正则 DoS。

### 7.3 日志

结构化日志统一通过递归 redactor，key 名大小写/连字符归一化后过滤 Authorization、api_key、password、
cookie、csrf、token、secret。HTTP access log 保持只记录 method/path/status，不记录 header/body/query
中的敏感值。异常信息进入日志前也执行高可信 value redaction。安全测试使用唯一假 secret 扫描响应、
数据库、RDF 与 journal。

## 8. SPARQL 与跨存储一致性

- R-006 现有 parser 继续拒绝客户端 `FROM`、`FROM NAMED`、`SERVICE` 和更新语句。
- 授权先把 Project/Ontology 转为当前允许 graph IRI，再调用
  `inject_dataset_clauses` 注入每图 `FROM + FROM NAMED`。调用方不能直接提交 Graph Set ID 或 graph
  IRI 扩大范围。
- `GRAPH ?g` 只能枚举注入的 named graphs；显式 `GRAPH <foreign>` 返回空，不退回全 dataset。
- Project/Ontology/Postgres scope 与 Oxigraph graph scope 在同一请求中共同校验；任一解析失败不得
  查询 RDF 后再过滤。
- 授权失败发生在写入前；现有 R-004 跨 Postgres/RDF recovery 仅处理已授权业务执行，不为未授权
  请求创建 Batch/Attempt/Audit。

## 9. 风险探针结论

1. **Oxigraph dataset 隔离：通过。** 2026-07-17 在真实 Oxigraph 写入两个唯一临时图；无 dataset
   查询返回 2 条，注入只含授权图的 `FROM/FROM NAMED` 后 `GRAPH ?g` 仅返回该图 1 条。两个图均已
   `DROP SILENT GRAPH` 清理。
2. **FastMCP 启动门：可行。** 当前 `FastMCP.run()` 是同步入口并立即进入所选 transport event loop；
   覆写 `run()` 可在任何 transport 启动前完成认证。当前 server 模块导入无运行副作用，registry
   检查可继续使用。
3. **审计承载：需要新表。** `semantic_edit_audits.warning_state` 可记录语义编辑 actor override，
   但登录、invalid/revoked key、授权失败和 key 生命周期没有共同父审计；独立只追加安全事件表是
   已确认功能契约所需的最小持久化。

## 10. 迁移、交付面与 rollout

实现至少涉及：

- migration、User/API key/security event repositories、password/key/session/bootstrap service；
- FastAPI authentication/CSRF、显式 route policy、Project resolver 和 auth/key endpoints；
- FastMCP authenticated run、runtime principal、tool policy和 actor 覆盖；
- 所有领域写路径的高可信秘密 scanner 与日志 redactor；
- frontend login/logout/me、CSRF/401 gate；
- REST/MCP/API/UI/architecture/config/requirements 文档与测试。

这是安全 hard cut：部署后除 health/login 外不再接受匿名请求，MCP 未配置 key 不启动。migration 与
bootstrap 配置必须在重启前准备；`.env.example` 和启动指南必须给出生成/配置步骤但不能含真实凭证。
实现提供一次性 operator bootstrap 命令：在数据库中创建持久运营 admin user/key，并把一次性明文仅
写入 gitignored 的 `backend/.local/ontology-platform-bootstrap.json`（目录 0700、文件 0600，命令拒绝
覆盖已有文件且输出只报告路径）。当前部署在首次 hard-cut
重启前必须运行该命令或等价的安全环境 bootstrap；运营主体不是测试夹具，独立测试清理不得撤销或
删除它。最终重启后必须用该主体验证 `/api/auth/me` 和至少一个受保护业务端点。测试主体继续使用
唯一后缀并按计划清理。

本仓库当前有独立 R-011 未提交工作；R-008 实现必须保留它，最终只提交可明确归属于 R-008 的 patch。

## 11. 验收标准

- HTTP、MCP、UI 三类主体真实认证成功，缺失/无效/revoked credential fail closed。
- read/model/admin 和全组织/Project-bound admin 的权限矩阵在 REST/MCP 一致。
- Project、Ontology、Build Session/Batch、Graph Set、Evidence、graph/query scope 均无跨 Project 泄漏。
- `GRAPH ?g`、显式 foreign graph、客户端 dataset/service 语法不能绕过授权范围。
- 所有写 audit actor 来自 principal；actor spoof 有安全事件且不改变 actor。
- key 明文一次展示、不可变、幂等撤销；安全事件持久且不含 secret。
- 合法凭证文档/占位符可建模，真实秘密在任何持久化前 422，响应/日志/DB/RDF 均无原文。
- UI 登录、CSRF、运行期 401、logout 和 service 重启行为符合契约。
- 共享测试计划、全量后端/前端、真实依赖、重启健康和独立测试全部通过。

## 12. Plan review 记录

### Round 1 - 2026-07-17 - REVISE

- `accepted-high`：原 Origin/Host 相等校验会被当前 Vite `changeOrigin=true` 代理破坏。改为显式
  `ONTOLOGY_UI_ORIGINS` 精确 allowlist，并要求真实 5173 -> 8001 代理正反向验收。
- `accepted-high`：当前部署无 API key/bootstrap user，若清理全部测试主体，hard cut 后只剩 health。
  增加一次性 operator bootstrap、0600 gitignored credential handoff、运营/测试主体分离和最终受保护
  端点验证。
- `accepted-high`：legacy Rule Definition 没有 Project 归属。新 definition 强制 Ontology 归属并链接
  `SemanticRuleModel`；legacy definition 仅 org admin；执行时强制 definition/Graph Set 同 Ontology。

修订后的需求、设计和测试计划交回同一 reviewer；Round 2 PASS 前不得开发。

### Round 2 - 2026-07-17 - PASS

- reviewer 确认 `ONTOLOGY_UI_ORIGINS` 与真实 Vite `changeOrigin=true` 路径的正反向验收闭环。
- reviewer 确认持久运营 bootstrap 主体、0600 credential handoff、测试清理和最终可用性闭环。
- reviewer 确认 Ontology-bound Rule Definition、legacy org-admin-only 和 execution 同范围约束闭环。
- 未发现新的 evidence-backed Critical/High 问题。

## 13. 冻结开发交接

- 需求：`docs/requirements-v1.0.md` R-008，本轮四项用户决策已写入。
- reviewed design：本文，plan review Round 2 `PASS`；Round 1 三项 High 均为 `accepted-high` 并修订。
- shared test plan：`docs/superpowers/plans/2026-07-17-r008-auth-authorization-test-plan.md`。
- git baseline：`2a1653e1eb02604cdf9f2b4749e4cca2f93b3be3`（`Align runtime interface documentation`）。
  R-011 在 plan review 期间由外部流程提交，冻结时工作区只剩 R-008 的
  `docs/requirements-v1.0.md` 修改及本文/共享测试计划两个新文件；后续仍须保留任何新出现的无关改动。
- developer 必跑：R-008 定向测试、全量 `cd backend && uv run pytest`、migration head、changed-file
  Ruff/format、`cd frontend && npm run build && npx playwright test`、`git diff --check`。开发阶段可做定向
  runtime 检查，但最终 service restart/health 和运营 bootstrap 可用性由独立测试与关闭阶段再确认。
- developer 不提交，不删除或改写 plan review/independent test history，返回显式 development-ready。

## 14. 实现结果与关闭记录

- 实现覆盖 migration、HTTP/UI/MCP 认证、scope 与 Project 授权、Rule Definition 归属、actor
  覆盖、安全事件、秘密扫描、operator bootstrap 和前端登录 gate；API、MCP、架构、UI、配置与
  运维文档已同步。
- 独立测试保留 Round 1/2 两个 High 的失败记录；修复后 Round 3 为 `PASS`，后端全量
  `689 passed, 3 skipped`，前端 Playwright `33 passed, 3 skipped`，迁移、Ruff/format、构建、
  真实依赖、策略 inventory、清理和 service health 均通过。
- 关闭阶段配置了固定 session secret，并通过 write-once bootstrap 创建持久运营 admin user/key。
  凭据仅落入 gitignored 的 `0700` 目录与 `0600` 文件；最终重启后 UI 登录、`/api/auth/me`、
  API key 访问受保护业务端点均为 200，匿名访问同一业务端点为 401。
