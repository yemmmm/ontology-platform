# v1 平台全链路验收设计

## 目标

以真实 PostgreSQL、Oxigraph、HTTP、MCP 和已启用认证的本地服务，证明 v1 平台从外部
建模 Agent 提交到后续 Agent 查询的核心协议能够作为一个整体工作。

本验收覆盖 `docs/requirements/requirements-v1.0.md` 的 R-001 至 R-008 及 R-011。它验证平台
契约，不评价外部 Agent 对 Dify 资料的建模质量，也不调用 Dify；该效果验证属于
`docs/requirements/requirements-v1.1.md` 的 R1.1-001。

## 当前行为与缺口

各 R-001 至 R-008 均已有定向测试和交付记录，R-008 还记录过全量回归。然而现有真实
浏览器 contract 测试主要通过 dataset load、直接编辑和规则执行验证运行时，没有将默认
工作区、Build Session、Lease、带 Evidence 的 Modeling Batch、lineage、Operation、
Context Query、MCP 和项目隔离放在同一条事务与恢复链路中。

## 验收契约

### 主链路

1. 已认证的管理员创建 Project 与 Ontology；新 Ontology 自动具有可用的默认工作区。
2. 为该 Project 创建 Build Session、Checkpoint 和目标 Ontology Lease。
3. 使用该 Lease 和当前 workspace version 提交带内联 Evidence 的 Modeling Batch，先
   dry-run，再 `apply_atomic`。
4. Batch 至少创建一个 Class、一个可查询的实例或关系、一个绑定该 Class 的 Operation；
   重试同一 idempotency key 不产生重复写入或 Evidence Association。
5. REST 查询得到 Evidence/lineage，Context Query 得到 Operation 与语义上下文；同一
   读取类请求经 MCP 返回等价核心状态。
6. 在同一 Project 中创建第二个 Ontology；Project-global 和显式多 Ontology Context Query
   均保留结果所属 Ontology，显式混入外部 Project Ontology 时拒绝而非静默收窄。
7. 服务重启后，Build Context、已应用 Batch、workspace version 和查询结果仍可读取。

### 失败与隔离链路

1. 已过期或错误的 Lease、过时 workspace version、以及故意无效的 atomic batch 被拒绝，
   不留下业务写入、Evidence 或 lineage 残留。
2. `apply_partial` 只持久化独立成功项；失败、blocked 或被其依赖的项不产生 Evidence
   Association 或 lineage。以受控 fault seam 制造跨存储不确定结果后，同一 idempotency key
   重试必须收敛，保留 fence，且不重复 RDF、Evidence 或 lineage。
3. Project-bound 主体不得读取、查询或引用另一 Project 的 Ontology、Evidence 或图；
   `GRAPH ?g` SPARQL 也不得扩大可见范围。
4. 请求中的伪造 actor 必须被认证主体覆盖；含高可信测试秘密的 Batch/Operation 在持久化前
   以 `secret_in_payload` 被拒绝，错误、审计与安全事件不回显该值。
5. MCP 进程在无 key 时拒绝启动；org admin 创建的短生命周期 Project-bound key 驱动独立
   stdio MCP 子进程，验证所属资源成功、P2 资源拒绝及启动认证。

## 边界与非目标

- 不重新交付 R-009、R-010 或任何 Pending 需求。
- 不运行外部模型，不评价自然语言答案、Dify 工作流或业务模型质量。
- 不改写现有单需求测试；新增场景只补跨需求的集成证明。
- 测试使用唯一前缀的 Project、Ontology 和图数据；仅在能证明归属时清理。

## 实现路径

新增后端端到端测试，使用真实迁移后的 PostgreSQL 与真实 Oxigraph，并通过运行中的 FastAPI
HTTP 边界走认证、Build Session 和 Modeling Batch 路由。MCP 使用 `mcp` stdio client 启动独立
`app.mcp.server` 子进程，不能以直接调用已注册 tool 函数替代 transport 与启动认证。

R-004 RDF 写入前，验收 harness 必须捕获原始 `SEMANTIC_PRODUCT_WRITE_MODE`，临时设为
`rdf_primary`，重启服务并验证实际模式；无论测试结果如何，都恢复精确原值并再次重启、健康
检查。受控的 recovery fault seam 只用于专用测试进程/fixture，不进入生产默认路径。

为避免测试运行状态与真实服务竞争，自动化测试的主链路在独立、唯一的 Project 下执行；真实
服务 smoke 在 systemd restart 后执行，不向现有业务 Project 写入。

## 完成标准

- 新增的全链路成功、失败/恢复、隔离场景都在真实依赖上通过。
- 普通 backend suite 和显式 PostgreSQL 并发 suite 全部通过。
- frontend build、带真实认证的 Playwright、接口文档同步检查通过；必测真实场景不可因缺
  API key 静默 skip。临时 Project-bound key 必须撤销，测试数据必须清理。
- `ontology-platform.service` 重启后 active，health、frontend 与受影响 API/MCP 检查成功。
- 验收记录、共享测试计划和需求/运行文档没有相互矛盾；变更作为独立提交关闭。
