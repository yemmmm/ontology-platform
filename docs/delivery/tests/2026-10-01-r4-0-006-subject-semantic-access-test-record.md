# R4.0-006 独立功能验收记录

## 范围与通过标准

依据 `docs/requirements/requirements-v4.0.md` R4.0-006 A1—A10 与
`docs/delivery/designs/2026-10-01-r4-0-006-subject-role-semantic-access-design.md`。
测试主体登记、项目成员、角色 Grant、Key 归属、HTTP/MCP 逐调用刷新、管理隔离、
受治理读取、cursor、依赖错误、生命周期与 fork 边界。开发自测不替代独立证据。
所有已执行用例满足预期且无未处置功能缺陷才判功能 PASS；未执行明确标 BLOCKED。
A11 的真实语义建模未获授权，本轮不启动 semantic start、不调用外部业务系统；
即使功能 PASS，整体需求仍保留 PARTIAL。

## 环境与证据边界

- 第一阶段使用 SQLite 外键开启的隔离数据库，真实 HTTP middleware 和 MCP
  `authenticate_runtime`／每调用认证；RDF 查询使用已有回归 fixture，只证明授权合同。
- 第二阶段待迁移及服务准备完成后使用真实 PostgreSQL/Oxigraph 和 test-owned 资源；
  不修改现有业务资源、run 或保留证据。持续 MCP 指同一存活实例连续工具调用。
- 不使用直接注入 AuthPrincipal 替代认证，不修改生产实现。仅拥有本记录与
  `backend/tests/test_r4006_independent.py`。

## 用例、步骤与预期

| 用例 | 条款 | 步骤 | 预期 |
| --- | --- | --- | --- |
| T01 | A1/A10 | API 登记用户、成员、角色与 read/model Key，读回 Key，提交旧直接 Grant/归属变更 | 归属明确、明文只创建展示，旧字段及归属修改 422 |
| T02 | A2/A3 | 同人多 Key、多项目同名角色、多角色 OR，删角色/清空分配 | 同项目共用并集，scope 独立；其他角色仍生效，普通读取保留 |
| T03 | A2/A4/A9 | read/model 配置控制面；Project Admin 访问全局/其他项目；替换跨项目角色 | 越权拒绝，错误角色集合完整拒绝且旧分配保留 |
| T04 | A4/A8 | 普通密码/session、管理员登录；管理员用户项目 read Key；有归属 org Key 禁用/降格；bootstrap | 普通不能登录/session；项目 read 不升权；org Key HTTP/MCP 下次失效，bootstrap 保留 |
| T05 | A5 | 显式业务角色映射、同名未映射、删除 RDF 定义 | 无自动授权，映射缺口可读修正，授权不依赖 RDF |
| T06 | A6 | 同 HTTP Key/持续 MCP 角色变更后重读；旧 cursor、相同有效 Grant 的角色替换 | 即时新权限；权限变更 mismatch；等价权限 cursor 可继续 |
| T07 | A7 | 精确/不存在、宽查询/关系/映射/Context/SPARQL/导出 | 无权隐藏在分页前且无控制面数据；通用 SPARQL scope 失败 |
| T08 | A8 | 禁用启用、撤销、移除重新加入、删除角色/项目、fork | 不可逆撤销、项目隔离、用户保留；fork 保护复制但不复制主体权限 |
| T09 | A9 | 空 Grant、损坏角色 JSON、数据库故障并恢复 | 空权限正常，依赖错误拒绝当前请求并可原凭据重试 |
| T10 | A10 | 角色 Grant 不改 API scope；检查 RDF/导出/工具边界 | 无外部数据/执行授权、无控制面进入语义图或授权推理 |

## 测试轮次

### Round 1 — 隔离认证测试（2026-10-01 20:59—21:02 +08:00）

代码基线 `a108a18688d68225d3a7a3eb71202eafa362c73d` 加开发中 R4.0-006 工作区。
命令（backend 目录）：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4006_independent.py -q`。
实际 **8 passed / 1 failed**（2.93s）。T01—T04、T06 主体刷新/cursor、T08 生命周期、
T09 损坏 Grant 恢复通过。T07 export 返回正确的 200 TriG，测试辅助函数错误地按 JSON 解码，
因此标记测试代码 FAIL，未判产品缺陷；已修正辅助函数按 Content-Type 解析，并以 RDF Dataset
检查导出，避免 compact prefix 影响。live PostgreSQL/Oxigraph 与完整 A5/fork 仍待执行。

### Round 2 — 补边界与相邻回归（2026-10-01 21:02 +08:00）

同一代码基线及工作区，补 T05 业务角色 API、T08 fork、T09 数据库故障恢复；复用首轮方案。
命令：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4006_independent.py tests/test_semantic_access_http.py tests/test_semantic_access_mcp.py -q`。
实际 **24 passed / 2 failed**（6.92s）。T07 导出解析为 FIXED；T05 fake 过宽匹配所有含
semanticDefinition 的查询，误向 resource route 返回 role-definition 行，修正为精确 SELECT
查询匹配。fork 新用例失败正在定位，保留失败结果。没有将未完成项标 PASS。

当前 Team Key 客户端尚未提交新必填 user_id；根据主 Agent 的权威范围复核，R4.0-007
负责该流程适配。006 管理 API 明确拒绝无归属 Key 是已批准行为，本测试不启动语义建模绕过合同。

#### F006-01 — Medium，fork 改写不透明 Grant（Round 2 FAIL）

复现：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4006_independent.py::test_independent_fork_keeps_protection_without_subject_assignments -q --tb=short`。
保护集 id=`g1`、allowed_grants=`["g1"]` 均合法，fork 后预期 Grant 原样保留，实际变成
`160253ee-bea6-547f-b6c3-68a386195c21`（另一个 g2 同样变成 UUID）。
根因 `CheckpointDataService.fork` 通用 remap 匹配任意平台 id；Grant 字符串不是身份引用。
主体、Key、角色不复制的断言通过；受保护资源配置保真失败。已报告主 Agent，请开发窄修复后复测。
随后主 Agent 修复仅 `SemanticProtectionSetModel.allowed_grants` 保持原值，未由测试方修改产品。

### Round 3 — fork 窄修复复测（2026-10-01）

同一基线加 F006-01 窄修复工作区。优先复测 T05 fixture 修正及 T08 fork，随后执行受影响
checkpoint 相邻回归及已有独立认证用例；live 条件尚待迁移。结果待命令完成后追加。

命令：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4006_independent.py tests/test_semantic_access_http.py tests/test_semantic_access_mcp.py tests/test_checkpoint_data.py -q --tb=short`。
结果：**32 passed / 1 skipped**（13.99s），T05 为 FIXED（测试 fixture），F006-01 为
**FIXED（产品）**；无回归。skip 是 opt-in 真依赖用例，未把 skip 当 PASS。
独立新增 12 tests 覆盖身份、多 Key、OR、原子角色替换、管理隔离、旧字段拒绝、普通 session、
组织 Key 禁用/降格、bootstrap、持续 MCP 刷新、Grant/SQL 依赖恢复、成员与项目生命周期、
有效权限 cursor、HTTP 受治理读取、业务角色映射缺口以及 fork 保真。
相邻回归另覆盖真实 HTTP middleware 的 Context、关系、映射、SPARQL 与 RDF 导出合同；
RDF fixture 仍非真实引擎证据。

### Round 4 — 成员存在性反例（2026-10-01）

开发方补齐 Project Admin 创建 Key 时的成员先行检查；测试方加入“存在但非成员”与
“全局不存在”两个 user_id 完全一致 404 的独立断言。
命令：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4006_independent.py::test_independent_project_boundaries_and_atomic_roles -q --tb=short`。
结果：**1 passed**（0.24s），T03 PASS，未发现 REGRESSION。
`uv run ruff check tests/test_r4006_independent.py` 与 `git diff --check` PASS。

### Round 5 — 真依赖 runtime（2026-10-01 21:11—21:13 +08:00）

命令：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. RUN_R4006_INDEPENDENT_LIVE=1 uv run pytest tests/test_r4006_independent.py::test_independent_live_http_and_persistent_stdio_mcp -q -s --tb=short`。
用例通过真实 HTTP 配置主体及角色、真实 RDF business-role 声明与实际 stdio MCP 子进程，
连续角色变更、禁用/启用后读回，最后清理并检查仅 test-owned 项目与用户。
基线 HEAD `71d0be3380bde24348752be1330aabd0e426561c` 加 006 工作区；期间 HEAD 前进为
007 文档审阅，006 产品代码未变化。主 Agent 已报告全量 **1075 passed / 39 skipped**、
真实 PostgreSQL 0033 upgrade、systemd active 与 HTTP 两端健康；这些为开发运行准备证据，
不计为本独立 Agent 的测试结果。

本轮实际 **1 passed**（4.33s）。真实 PG/Oxigraph + `127.0.0.1:8001` HTTP + 单个持续
`python -m app.mcp.server` stdio 子进程，先完成实际 initialize/authenticate，再连续工具调用：

| 当前配置 | HTTP 精确受限资源 | 同一 MCP 子进程 RDF 导出 |
| --- | --- | --- |
| 无角色 | 404 | 不含受限 subject |
| 管理提交分配 private Grant | 200 | 含受限 subject |
| 管理提交清空角色 | 404 | 不含受限 subject |
| 用户禁用 | 401 | 凭据无效，ok=false |
| 用户重新启用 | 404（仍无角色） | 凭据恢复，仍不含受限 subject |

真实 business_role semanticDefinition 的显式关联读回 valid；随后删除该 RDF 声明，管理读回
missing，角色 Grant 仍为 `["private"]`。没有重启子进程或服务，没有访问外部业务数据／执行服务。

自有 source Project `d78c3d47-27cd-4215-9d11-0f75d1cabf07`、Ontology
`118f9336-c9a5-4181-91a6-c0751fcf00f1`、graph set `cfddd284-99e5-587a-99db-2e76709b897a`。
项目/users/Keys/角色/保护集与 RDF graph 已清理；后续 cleanup 核对发现通用 graph registry／set
不会随 Project SQL CASCADE 删除，已按已有 checkpoint live 清理模式补齐 test cleanup。
对上述确切自有 Ontology 的 **4** 条 registry 及上述 graph set 做补清理并断言不存在；
没有清理现有业务资源、审计或失败证据。

### Round 6 — 完整自有资源 cleanup 复核（2026-10-01 21:13 +08:00）

仅测试 finally 增加 graph set/member、registry/state/revision 的精确自有身份清理与不存在断言，
产品输入不变。再次执行同一 live 用例（去 `-s`）：**1 passed**（5.19s）。
RDF graph_exists=false、PG 项目/users/registry/set 无残留断言全部通过；RDF graph、Key、成员、
角色与分配的清理保持 test-owned 范围，必要 SecurityAudit 记录保留。
`uv run ruff check tests/test_r4006_independent.py` 和 `git diff --check` PASS。

## 最终独立判定

**A1—A10 功能 PASS；F006-01 FIXED，无未处置产品缺陷。**

| 条款 | 判定与证据边界 |
| --- | --- |
| A1 | PASS：真实 HTTP 用户/成员/角色/Key 创建读回，空权限普通读取、一次性明文 |
| A2 | PASS：多 Key、多项目、同名角色独立、跨项目非法配置不改变原集合 |
| A3 | PASS：多角色并集、保护集 OR、角色删除/全部移除不保留旧 Grant |
| A4 | PASS：read/model 控制面拒绝、Project Admin 项目隔离与目录存在性反例、普通密码/session 拒绝、管理员 read 不升权 |
| A5 | PASS：真实 RDF 显式业务角色关联与删除缺口；同名无自动关联；控制面不进入语义读回/导出（代码边界与过滤用例） |
| A6 | PASS：HTTP 与持续实际 stdio MCP 新调用即时更新；有效权限 cursor 单元验收覆盖变更 mismatch 与等价角色可继续，原路由相邻回归通过 |
| A7 | PASS：角色链下精确/宽查询、关系/映射、Context、SPARQL、导出过滤；HTTP/RDF 导出含真引擎证据，其余复用既有 fixture 授权合同 |
| A8 | PASS：禁用/启用、组织 Key 禁用/降格与 bootstrap、成员移除再加入旧 Key 失效、删角色/项目隔离、fork 不复制主体链且保护配置保真；fork 为隔离功能证据 |
| A9 | PASS：损坏 Grant 与 SQL 查询故障为 dependency_error，可原凭据重试；空权限成功、跨项目替换失败原配置完整 |
| A10 | PASS：旧 semantic_grants/归属覆盖字段 422；Grant 不提高 scope；生产边界无外部授权/执行能力扩展，不调用外部业务系统 |

**A11 / L1 真实语义未授权、未执行；整体需求 PARTIAL。** 本轮没有新建或继续任何 semantic
modeling start，fixture／真引擎的授权功能验证不能证明实际业务模型职责或建模质量。
当前 Team Key 调用方接入新 user_id 合同的限制仍留给 R4.0-007，未伪装已交付。
测试文件与记录已冻结；无需因未变化产品重复全量验证。
