# R-008 API/MCP 认证、授权与项目隔离共享测试计划

## 1. 测试依据与记录规则

- 需求：`docs/requirements-v1.0.md` R-008。
- 设计：`docs/superpowers/specs/2026-07-17-r008-auth-authorization-design.md`。
- 依赖：R-001 Project/Ontology、R-003/R-004 构建写入、R-005 lineage、R-006 scoped query、
  R-007 Operation secret boundary。

开发 Agent 和独立测试 Agent 必须复用本计划。独立测试在第 10 节追加 Round，不覆盖此前记录；
修复后继续追加下一 Round。

## 2. 审查重点

1. 是否存在任何 HTTP route、MCP tool 或 service 写路径绕过认证、scope、Project resolver 或 actor
   override。
2. 全组织 admin 与 Project-bound admin 是否严格区分，是否可借 Project/key CRUD 提权。
3. SPARQL dataset 限制是否在真实 Oxigraph 对 `GRAPH ?g`、显式 graph 和复杂 query 都有效。
4. secret 是否可能先写入 Batch/Audit/log 再被校验，或合法 API 文档是否被误拒。
5. R-008 hard cut 是否仍能通过 bootstrap、本地 UI、测试 fixture 和 MCP 启动完成真实接入。

## 3. 必测场景

### A. 密码、API key、session 与 bootstrap

- Argon2id 密码 hash 有独立 salt，同密码产生不同 hash且都可验证；明文/SHA-256 不用于密码。
- API key 使用规定格式和 32 位 base62 随机体；DB 只有 SHA-256 hash，创建响应只展示一次。
- list/get 不返回 hash/明文；Project/scope 不可修改；revoke 首次与重复调用都成功且时间稳定。
- revoked/不存在/畸形 key 返回相同 401，响应与安全事件不含 key，不能用错误差异枚举。
- bootstrap user/key 首次创建和重复启动幂等；两项 user 配置只设置一项时拒绝启动；全部未设置只
  warning。不同 bootstrap key 不暗中覆盖已有不可变 key。
- session cookie 包含 HttpOnly/SameSite/expiry，生产 Secure；内容无密码/key。有效 session 可访问，
  篡改/过期/session_version 不符返回 401。
- login 不存在用户和错误密码返回相同响应；连续失败触发有界 429，窗口结束后恢复；成功登录清零
  对应失败状态。
- logout 清除 session/CSRF cookie；重启在固定 SECRET_KEY 下保持 session，在临时 key 下旧 session
  失效且有 warning。

### B. HTTP 认证、CSRF 与 route coverage

- 三个 health 和 login 匿名可用；其他 `/api`、OpenAPI 和 docs 匿名均 401。
- bearer、session 分别可用；同时携带不同主体返回 401并记录事件。
- session 的 POST/PATCH/PUT/DELETE 缺少或错误 CSRF、foreign Origin 均拒绝；正确 double-submit
  通过。真实浏览器经当前 5173 -> 8001 Vite `changeOrigin=true` 代理的合法 Origin 必须成功，伪造
  foreign Origin 必须失败；测试不能只用 Host 与 Origin 相同的 TestClient。Bearer 请求不要求 CSRF。
- 前端通过同源 `/api` 登录，刷新后 `/auth/me` 恢复主体；运行期 401 回登录页；logout 后受保护请求
  失败。
- 自动枚举 FastAPI runtime route，除显式公开项外每个 operation 都有 scope policy；新增未分类 route
  的测试夹具必须失败。

### C. Scope 与管理权限矩阵

使用 Project P1/P2，分别创建 P1 read/model/admin key、P2 key 和 org admin：

- read 可读 P1，不能写；model 可读写 P1，不能管理 Ontology/key；admin 包含 model/read。
- P1 任一 Project-bound key 都不能读 P2；显式 P2 返回 403，opaque P2 resource 返回 404且无内容。
- org admin `GET /projects` 返回 P1/P2；P1 key 只返回 P1。
- 只有 org admin 可 create/update/delete Project和 create/revoke org key。
- P1 admin 可管理 P1 Ontology与 P1 key；不能操作 P2 key/Ontology、不能创建未绑定 key，也不能授予
  超过自身权限的 scope。
- key 创建、撤销、越权均产生最小安全事件；普通成功 GET 不产生安全事件。
- P1 model/admin 新建 Rule Definition 时必须指定 P1 Ontology；列表只含 P1 definitions。P2 definition
  opaque ID 对 P1 返回 404；P1 definition 对 P2 Graph Set 的 rule/construct execution 在执行前拒绝。
  `semantic_rule_id=null` 的 legacy definition 对 Project-bound 主体不可见，仅 org admin 可管理。

### D. 资源归属

REST 与 MCP 至少分别验证：

- Project、Ontology、Build Context/Session/Checkpoint/Lease、Modeling Batch/Attempt；
- Evidence Artifact、Chunk、Evidence Reference/Association、Fact Evidence；
- Graph Registry、Graph Set/members/history/diff、Rule/Reasoning/Projection/Migration；
- Context Query、SPARQL、read model、lineage/export。

对 P1 principal 输入 P2 的路径 ID、body project_id、ontology_id、graph_set_id、evidence ID 或混合
线索时 fail closed。无法解析 Project 的 ad-hoc/legacy graph/migration scope 对 Project-bound 主体拒绝，
org admin only 的治理路径正常。授权失败前后 Postgres/RDF revision、Batch/Audit 数不变。

### E. MCP

- `ONTOLOGY_MCP_API_KEY` 缺少、无效、revoked 时 stdio server 在 event loop 前非零退出且错误无秘密。
- 有效 key 启动；运行中撤销后下一 tool call 失败，无需重启。
- 自动枚举 FastMCP registry，每个 tool 有 required scope 和 Project resolver 分类。
- read/model/admin 与 P1/P2 矩阵对 REST/MCP 同一能力返回一致核心结果/错误。
- tool payload actor 不能覆盖 runtime actor；spoof 产生安全事件。
- MCP module import/registry 文档检查不要求 key，不会意外连接数据库或启动 transport。

### F. SPARQL 隔离

- 真实 Oxigraph 中 P1/P2 各有唯一 marker；P1 Project/global Ontology scope 只能返回 P1 marker。
- `GRAPH ?g`、显式 `GRAPH <P2 graph>`、nested subquery、ASK/CONSTRUCT/DESCRIBE 均不泄漏 P2。
- 客户端 `FROM`、`FROM NAMED`、`SERVICE`、update、畸形 query 在查询前拒绝。
- 注入 dataset 只含已授权且当前 ready 的 graph；Project partial 与显式 Ontology all-or-nothing 保持
  R-006 语义。
- raw Oxigraph control query 证明 P1/P2 marker 同时存在，避免把“无泄漏”误判为测试数据缺失。

### G. Actor 与安全事件

- API key 写入 actor=`key:<name>`，UI 写入 actor=`user:<username>`，覆盖 Semantic Edit、Modeling
  Batch、Evidence、Brief/Question、Rule/Reasoning/Projection 等有 actor 的路径。
- payload actor 缺省无 warning；相同 actor无 spoof；不同 actor 被忽略，domain audit 使用 principal，
  security event 为 `actor_spoof_attempt`，且 event/detail 不保存伪造原文。
- login success/failure、invalid/revoked key、forbidden scope/project、key create/revoke 事件持久化；
  Project 删除后对应事件仍存在。
- event API 不存在；数据库行不可通过产品 route 更新/删除。业务事务回滚不吞掉授权失败事件。

### H. Secret scanner 与日志

- 合法术语 `api_key/password/Authorization`、Operation credential requirement、`<TOKEN>`、
  `${API_KEY}`、REDACTED、`***` 和文档型 Bearer 占位符可保存并查询。
- 完整平台 key、JWT、AWS key、非占位 Bearer token 分别在所有领域写入面返回
  `422 secret_in_payload`。
- Modeling Batch 在 Batch/Item/Attempt/Finding/content hash 创建前拒绝；Semantic Edit 在 RDF/Audit/
  revision 前拒绝；Evidence/Brief等在 Postgres row 前拒绝。
- 响应、security/domain audit、Postgres JSON/text、Oxigraph、应用日志和 journal 对唯一假 secret
  全部零命中；error 只含 pattern category。
- auth password/header和 key create 明文能通过专用认证通道，但不进入领域 scanner、日志或 audit。
- scanner 在最大允许请求边界内完成，无灾难性正则回溯；超限请求沿用现有限制。

### I. Regression、migration 与 frontend

- migration 从 0026 升级到新 head成功；现有 api_keys 数据保持可读，非法 legacy scopes fail closed；
  downgrade/upgrade（若仓库惯例要求）不丢无关数据。
- 现有 R-003/R-004/R-005/R-006/R-007 定向测试在认证 fixture 下保持通过。
- API/MCP runtime inventory和 R-011 文档同步测试通过，不覆盖当前独立 R-011 工作区。
- frontend 登录页、错误态、logout 和已有工作区基本导航 Playwright 通过；无 key/password 写入
  localStorage/sessionStorage。
- 全量 backend pytest、frontend build、全量 Playwright、changed-file Ruff/format、diff check通过。

## 4. 建议自动化命令

文件名可按实现调整，覆盖必须等价：

```bash
cd backend
uv run alembic upgrade head
uv run pytest \
  tests/test_authentication.py \
  tests/test_authorization.py \
  tests/test_api_keys.py \
  tests/test_security_audit.py \
  tests/test_secret_scanner.py \
  tests/test_mcp_auth.py \
  tests/test_semantic_context_query_api.py \
  tests/test_modeling_batches_api.py -q
uv run pytest
uv run ruff check <changed-python-files>
uv run ruff format --check <changed-python-files>

cd ../frontend
npm run build
npx playwright test

cd ..
git diff --check
```

## 5. 真实运行态验收

所有夹具使用唯一 `r008-<timestamp>` 后缀：

1. migration 后以 bootstrap admin 登录 UI，创建 P1/P2、两套 Ontology 和各 scope key。
2. 真实 HTTP 分别执行 read/model/admin allow/deny 矩阵；检查 security events 和 actor。
3. 用 P1/P2 graph marker 执行 scoped SPARQL attack matrix并用 raw control query证明数据存在。
4. 以 P1 MCP key 启动真实 stdio MCP，执行 read/model/foreign Project场景；撤销 key 后再次调用。
5. 分别提交合法 credential 文档和唯一假 secret；扫描 HTTP、DB、Oxigraph 与 journal。
6. 浏览器执行 login -> workspace read -> model write -> refresh -> logout；检查 CSRF 和存储。
7. 重启 service，重复 session/key/health与最小 Project query，确认持久化和配置行为。
8. 只清理由唯一后缀证明归属的 Project、key、user/graph测试数据；security events按契约保留，不能证明
   归属的数据不删除。

首次 hard cut 前还必须通过 operator bootstrap 或等价安全环境配置创建一组无测试后缀的持久运营
admin user/key。一次性明文只落在 gitignored、权限 0600 的本地 credentials 文件，不出现在命令输出、
git diff、日志或测试计划。该主体不属于第 8 步清理范围；测试主体清理与最终重启后，用运营主体调用
`/api/auth/me` 和至少一个受保护业务端点并得到 200。

## 6. 重启与健康门槛

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

还要验证匿名受保护 route 返回 401、配置 key 后 MCP 可启动、缺 key MCP 非零退出。失败时检查：

```bash
journalctl --user -u ontology-platform.service --no-pager -n 300
```

journal 输出不得包含测试 secret/password/key。

## 7. 清理规则

- 删除前用唯一后缀和 Project/Ontology 关系双重证明 ownership。
- 精确撤销/删除测试 key与用户；精确 drop 测试 Ontology 的已知 graph IRI。
- 不撤销或删除无测试后缀的持久运营 bootstrap user/key；清理后必须验证部署仍可认证使用。
- `security_audit_events` 是验收对象且按需求只追加，不通过产品代码删除；测试事务内的单元夹具可回滚。
- 临时 systemd manager environment 必须恢复；不得遗留 bootstrap password/key。

## 8. 完成门槛

- plan review无未处置 Critical/High；实现与 reviewed design一致。
- 独立测试在本计划追加 PASS，所有历史失败保留并标记 fixed/accepted。
- 真实 PostgreSQL/Oxigraph/MCP/browser 和 secret journal scan通过。
- backend/frontend全量、migration、静态、diff、restart/health通过。
- requirement、design、API、MCP、architecture、UI、config/README状态一致。
- 只提交 R-008 可归属 patch，不夹带现有 R-011 或其他用户改动。

## 9. Plan review 记录

### Round 1 - 2026-07-17 - REVISE

- `accepted-high`：增加真实 Vite proxy Origin/Host 分离条件下的合法/foreign CSRF 验收。
- `accepted-high`：增加持久运营 bootstrap 主体、0600 credential handoff和清理后可用性门槛。
- `accepted-high`：增加 Ontology-bound Rule Definition 的 P1/P2 list/get/execute 隔离矩阵。

修订后待 Round 2 复审。

### Round 2 - 2026-07-17 - PASS

- 三项 Round 1 `accepted-high` 均已在需求、设计和本计划形成实现与验收闭环。
- reviewer 未发现新的 Critical/High；可进入冻结开发交接。

## 10. 独立测试记录

`requirement_tester` 在此追加 Round，不覆盖前一轮。

### Round 1 - 2026-07-17 - FAIL

- `High`：未解析的资源归属被当作允许，而不是 fail closed。独立运行态验证中，
  Project-bound model 主体在应被拒绝的 REST 及 MCP 路径上均观察到成功，不满足
  Project 数据隔离契约。
- 自动化结果：R-008 定向测试 `37 passed`；后端全量 `683 passed, 3 skipped`；前端
  Playwright `33 passed, 3 skipped`；前端构建、迁移、Ruff、格式与 diff 检查通过。
- API key GET/list 边界独立验证通过：read/model 无法列出或读取 key metadata，
  Project admin 只能读取同 Project metadata。
- 本轮创建的临时项目、身份、key、Graph Set 和图数据均已精确清理；未修改
  systemd manager environment。其余完整资源隔离、真实浏览器和重启矩阵留待修复后下一轮。

### Round 2 - 2026-07-17 - FAIL

- Round 1 缺陷路径已修复：未归属 dataset 写入、ad-hoc Graph Set 的 REST 创建/读取以及
  MCP 读取均被拒绝；同 Project、Ontology-scoped Graph Set 的 REST 创建/读取和 MCP 读取
  均成功，foreign Project MCP 被拒绝，运行中 revoke 立即生效。
- `High`：Project-bound MCP 主体仍可调用一个无资源参数的全局状态变更能力，因该能力
  未纳入 org-only 策略，实际导致另一 Project 的持久状态被修改。这不满足 Project
  隔离和 fail-closed 契约。
- 修复影响面定向自动化 `30 passed`；上述 REST/MCP/Oxigraph/PostgreSQL 路径均在真实运行态
  验证。因新 High 缺陷，本轮未重复全量 backend/frontend、真实浏览器、secret 零持久
  和 service 重启门槛，留待修复后下一轮。
- 本轮唯一后缀的临时 Project、Ontology、key、Graph Set、derived pointer 和图数据已清理；
  复核计数均为 `0`，未修改 systemd manager environment，未触碰无关 v1.1/R-010 工作。

### Round 3 - 2026-07-17 - PASS

- Round 1/2 的两个 `High` 已关闭：未解析资源归属按 fail closed 处理；55 个 MCP tool 均有
  `required_scope`、ownership 和 mutation 分类，其中 45 个 Project-resource、9 个 org-only、
  1 个只读 global-safe，29 个状态变更能力均非 global-safe；此前遗漏的全局状态变更能力已有
  org-only 回归保护。
- 当前稳定工作区重新执行 R-008 定向测试 `32 passed`，后端全量 `689 passed, 3 skipped`；
  Alembic current/head 均为 `0027_r008_auth`，迁移回归包含在全量测试内；45 个变更 Python 文件
  Ruff 与 format check、`git diff --check` 均通过。
- 前端构建通过；Playwright `33 passed, 3 skipped`，其中 3 项是需要 live key 的既有条件跳过，
  登录/登出与通用错误态浏览器用例已通过。服务已在最终代码后重启并保持 active，backend/frontend
  均返回 200；匿名业务 route、OpenAPI 和 docs 均返回 401，MCP 无 key 非零退出。
- 运行态普通复核未发现新增缺陷：Project/Ontology/RDF 中唯一 R-008 测试后缀计数均为 0；
  systemd manager 临时环境项为 0；journal 对平台 key、Bearer 值和 password JSON 的模式匹配均为
  0。安全审计事件按契约保留，不作为测试数据删除。
- 当前部署尚未配置固定 session secret，也尚未创建无测试后缀的持久运营 user/key 与 0600
  credentials 文件。这不是代码缺陷：bootstrap 的一次性 password/key handoff、0600 权限和
  write-once 行为已有自动化验证；但它是 requirement closure 的强制运营待办。主 Agent 在宣告
  R-008 完成前仍须配置固定 secret、运行 operator bootstrap、重启，并用该运营主体验证
  `/api/auth/me` 和至少一个受保护业务端点返回 200；该主体不得随测试数据清理。

### 关闭阶段补充 - 2026-07-17 - COMPLETE

- 已在 gitignored 的本地配置中设置固定 session secret；已创建一组无测试后缀的持久运营
  admin user/key。credentials 目录权限为 `0700`、文件权限为 `0600`，包含 username、初始
  password、API key ID 和一次性 API key，所有字段非空且未进入命令输出、日志或 Git diff。
- 最终 service restart 后 unit 为 active，backend health 与 frontend 均为 200；运营 UI 登录、
  `/api/auth/me`、运营 API key 的 `/api/auth/me` 和受保护 Projects 读取均为 200，匿名 Projects
  读取为 401。数据库复核为 1 个运营 user、1 个有效 org-admin key。
