# R3.0-005 Ontology 引导的 SQL 问数链路 — 功能设计

- 日期：2026-08-27
- 状态：plan review **PASS**（2026-08-27，两项 High 修订后窄幅复审通过；未实现）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-005（§4 表行 P0，概要设计已冻结）
- 概要设计基线：
  `docs/delivery/designs/2026-08-25-v3-0-remaining-requirements-outline-design.md` §5
- 冻结依赖合同：
  - `docs/delivery/designs/2026-08-26-r3-0-003-relational-schema-mapping-design.md`
    （映射/指标词汇、detail 模板 `detail_fields` 承载面、context:query `mapping`/`metric` 类型）
  - `docs/delivery/designs/2026-08-23-r3-0-004-semantic-knowledge-authorization-design.md`
    （与不存在不可区分、无痕过滤合同——本设计逐字复用、零改动）
- 场景数据基线：`docs/evaluation-scenarios/industrial-service-v3/`（R3.0-001，
  `industrial_service_v3` schema + 安全装载器 `scripts/load-industrial-service-v3-postgres.sh`）
- 共享测试计划：
  `docs/delivery/test-plans/2026-08-27-r3-0-005-ontology-guided-sql-qa-test-plan.md`
- 交付边界：交付**平台外**最小 SQL 执行适配器（repo-local 脚本）+ Consumer Agent 问数链
  （机械 SQL 生成链 + 少量真实 LLM 冒烟轮）+ 验收证据。后端产品代码预期**零改动**；
  无新表、无新 API、无新服务；真实建模与完整端到端验收归 R3.0-006。

## 1. 目标

1. **SQL 执行适配器（平台外，repo-local）**：一个进程式小脚本——stdin 收一个 JSON 请求、
   在 PostgreSQL 执行单条 SQL、stdout 回一个 JSON 结果（列/行或数据库错误）；DSN 只来自
   环境变量；连接级只读（`default_transaction_read_only=on`）作为共享基线的最小数据安全。
2. **Consumer Agent 问数链**：接收自然语言问题与服务端绑定主体 → 经 MCP 语义读取面
   （`query_semantic_context` / `get_semantic_read_model`）取得**授权后**的概念、关系、指标
   口径与 Schema 映射 → 生成可解释 SQL → 交适配器执行 → 基于结构化结果回答并说明所用
   业务口径。
3. **无法确认合同**：授权语义不足以安全生成 SQL 时，链路必须终止于"无法确认"，不区分
   未建模、不存在或无权可见；不得回退原始 Schema 猜测，不得使用授权上下文中未出现的
   表、列、join path 或指标。
4. **双层验收（用户已确认的组合）**：
   - 确定性机械 pytest：适配器合同 + 授权语义读取 → SQL 生成 → 执行 → 结果比对全链正确性；
   - 3–5 轮真实 LLM Consumer Agent 冒烟：证明授权语义足以生成正确 SQL、缺失授权/语义缺口
     正确返回无法确认。
5. **不消耗建模授权**：冒烟轮只使用 read 主体，不发生 modeling start，不消耗三次建模
   attempt 预算；R3.0-006 仍需用户显式授权。

## 2. 非目标

1. 不实现数据授权、SQL 重写、策略引擎、语义校验、查询审计、平台 Connector（需求原文边界；
   词汇表 SQL Execution Adapter 的 Avoid 清单逐条适用）。
2. 不做 NL2SQL 模型/prompt 工程、SQL AST/静态检查/沙箱/资源配额、数据源连接器框架、
   生产级行列权限与多租户策略（概要设计 §5.4 暂不细化项，不得静默晋升）。
3. 不新增后端表、API、服务或 migration；适配器不注册为 MCP 工具、不进入 `backend/app/`。
4. 不做真实工业售后场景建模与端到端验收（R3.0-006）；不新增场景内容（只复用 R3.0-003
   fixture 形态与 R3.0-001 数据基线）。
5. 不改 R3.0-003/R3.0-004 已交付的读取面与授权合同；若发现读路径缺口，只修最窄失败层
   （§4.3）。
6. 不宣称业务数据安全成立：适配器只读不是策略引擎，生产替换边界必须成文（§3.2）。

## 3. 功能合同

### 3.1 交付组成与位置

| 部件 | 位置 | 形态 |
| --- | --- | --- |
| SQL 执行适配器 | `scripts/r3-0-005/sql_exec_adapter.py` | 进程式脚本：stdin JSON → 执行 → stdout JSON；DSN 取自环境变量 `R3005_SQL_ADAPTER_DSN` |
| 机械验收测试 | `backend/tests/test_r3005_sql_exec_adapter.py`、`backend/tests/test_r3005_authorized_sql_chain.py` | pytest（只加测试文件，不改产品代码） |
| Consumer Agent 冒烟驱动 | `scripts/r3-0-005/consumer_smoke.py`（+ 冒烟问句与判分清单） | repo-local 小脚本：按主体 key 启动带平台 MCP 语义读取工具与适配器 shell 调用能力的 LLM Agent 运行时，录制全程转录 |
| 证据 | `docs/delivery/evidence/2026-08-27-r3-0-005/` | 转录、SQL、适配器响应、判定清单 |

（适配器与驱动是平台外验收工具，不是平台组件；命名与路径可在实现期微调，合同不变。）

### 3.2 SQL 执行适配器合同

- **输入**：stdin 一个 JSON 对象 `{"sql": "<单条 SQL 语句>"}`；未知字段、非对象、非字符串
  `sql` → `input_error`（fail-closed）。SQL 不从命令行参数读取（杜绝 shell 注入面）。
- **输出**：stdout 恰好一个 JSON 对象：
  - 成功：`{"ok": true, "columns": [...], "rows": [[...], ...]}`；
  - 失败：`{"ok": false, "error": {"kind": "database_error" | "input_error" | "config_error",
    "message": "<数据库/适配器原始错误信息>"}}`。
  - 进程退出码：`ok=true` → 0；`ok=false` → 1。stderr 只允许诊断性短文本。
- **连接**：DSN 只来自环境变量 `R3005_SQL_ADAPTER_DSN`（缺失 → `config_error`）；缺省部署
  下指向承载 `industrial_service_v3` 的 Compose PostgreSQL（默认映射宿主端口 5434）。
- **连接级只读（最小共享基线数据安全）**：连接参数固定附加
  `options=-c default_transaction_read_only=on`；任何写事务（INSERT/UPDATE/DELETE/DDL，
  含 `WRITE` 型 CTE）由 PostgreSQL 以 read-only transaction 错误拒绝，按 `database_error`
  透传，数据零变更。**这是工程兜底，不是策略引擎**——它不区分主体、不做行列裁剪。
- **单语句**：一次调用执行一条语句（驱动层天然拒绝多语句拼接）。
- **明确不做**：授权判定、SQL 重写、语义校验、审计落盘、限额、缓存、连接池、Connector
  框架、方言适配（仅 PostgreSQL）。
- **生产替换边界（成文义务，需求原文）**：进入真实生产前，本适配器必须被替换或包裹为
  由外部系统按用户 ID、租户、组织、行/列策略实施的数据安全边界（词汇表 Business Data
  Authorization）；本交付的验收结论**不得**被解释为业务数据安全已成立。

### 3.3 Consumer Agent 问数链（六步映射）

1. 接收自然语言问题与服务端认证主体（冒烟轮经 MCP 进程的 `ONTOLOGY_MCP_API_KEY` 绑定
   `runtime_principal`，与 R3.0-004 合同一致）。
2. 查询授权后的语义上下文：`discover_semantic_scopes` 定位项目 → `query_semantic_context`
   （`resource_types` 含 `mapping`/`metric`，候选 `data` 携带引用拓扑）定位与分类 →
   `get_semantic_read_model`（`entity_iri` 精确读取四类 detail 模板）取得全部口径字段
   （R3.0-003 冻结的字段承载面；`resources/{iri}` 与 anchor 只做定位）。
3. 判断语义是否足以生成 SQL；不足 → **无法确认**（§4.2），不区分未建模/不存在/无权可见。
4. 仅使用本次授权上下文中出现的表、列、join 步骤、枚举含义、指标口径生成 SQL
   （含 `op:valueExpression` 计算说明的**消费方解释**，如
   `repairDuration = resolved_at − opened_at` → EXTRACT/EPOCH 表达式）。
5. SQL 交适配器执行，取回结构化列/行或数据库错误。
6. 基于结果回答，并说明所用业务口径（指标名、聚合、粒度、时间字段、过滤、空值/分母规则）
   与关键映射依据。

Agent 不读取保护集定义、成员清单或 grant（平台面本就 model-scope 限定），也不能从结果
缺失推断隐藏资源。

### 3.4 机械 SQL 生成链（确定性，测试侧）

机械 pytest 内以固定规则从授权读取面推导 SQL（规则属于测试/断言层，不是产品代码）：
指标 → `SELECT <aggregation>(<measure 列或 valueExpression 推导表达式>) FROM <主表>
[join 步骤按 JoinMapping 顺序机械拼接] WHERE <filters：属性 IRI→列、operator→声明式
比较、枚举值经 EnumValueMeaning 校验> GROUP BY <grain 属性 IRI→列>`；全部标识符必须
能在授权 `detail_fields` 中找到出处（出处不闭合 → 该链必须输出无法确认终态）。
无权主体链路在任一必需资源缺失时终止于无法确认终态——这是对 R3.0-004"与不存在一致"
合同在 SQL 消费侧的确定性复证。

### 3.5 冒烟问句集（3–5 轮，真实 LLM）

| # | 主体 | 问句 | 期望 |
| --- | --- | --- | --- |
| Q1 | 持映射授权 read key | 状态为已完成（RESOLVED）的工单有多少 | 正确计数；SQL 只用 fixture 映射内的表/列/枚举含义；答案说明口径 |
| Q2 | 同上 | 各设备型号的平均维修耗时（小时） | 多跳 join（work_orders→incidents→assets→equipment_models）+ 指标口径正确；数值与机械基准一致 |
| Q3 | 无 cost grant read key | 备件的平均标准成本是多少 | **无法确认**：不区分原因、不提权限/保护集、不产生针对成本列的 SQL 或数值 |
| Q4 | 持 `cost-visibility` grant read key | 同 Q3 | 正确数值；SQL 含受保护指标口径引用 |
| Q5 | 持映射授权 read key | 各仓库的库存变动情况如何（**语义缺口 fixture**：warehouses/inventory_movements 故意不建映射） | **无法确认**；不得回退原始 Schema（转录中无 information_schema/PG catalog 查询、无对未映射表的 SQL） |

问句措辞可微调，覆盖面不变：(a) 正向运营语义、(b) 无成本授权、(c) 故意语义缺口。
判定与记录方式见共享测试计划 §8。

### 3.6 测试数据复用（零新场景内容）

- **RDF/语义侧**：复用 R3.0-003 fixture 形态（类、属性、TableMapping/JoinMapping/
  EnumValueMeaning/MetricDefinition、保护集与双 key），把 fixture 的 `tableName`/列**重定位**
  到 R3.0-001 已装载的 `industrial_service_v3` 真实表（fixture 调整，非新场景内容；
  名称只存在于测试数据）。保护集 `PS_COST`（`allowed_grants=["cost-visibility"]`）成员 =
  成本指标 IRI + `standardCost` 属性 IRI + 备件表映射 IRI（H-B 整行隐藏语义使无权主体
  连备件表映射都不可见）。
- **PostgreSQL 侧**：仅由既有安全装载器
  `./scripts/load-industrial-service-v3-postgres.sh` 装载；不新建任何表。

### 3.7 建模授权边界

fixture 语义内容经 `KEY_MODEL` + Modeling Batch（dry-run → apply）seeding（R3.0-003 先例，
走真实产品写路径；seeding 批次 ID 登记为基线）。**fixture 落成之后**，冒烟轮与机械链均为
只读消费，不再创建 Build Session / Modeling Batch、不发生 modeling start，不消耗三次建模
attempt 预算；R3.0-006 启动真实建模仍需用户显式授权。

## 4. 错误与边界

### 4.1 适配器错误分类

`config_error`（DSN 缺失/不可解析）、`input_error`（载荷非法/多语句）、`database_error`
（PostgreSQL 原始错误，含 read-only 拒绝、对象不存在、权限拒绝）——均单 JSON 返回，
不 stacktrace 外溢、不重试、不部分输出。

### 4.2 无法确认呈现（Agent 侧合同）

- 措辞中立：包含"无法确认"语义，不说明"未建模/不存在/无权限"哪一种；
- 不泄露：不出现受保护资源 IRI/label/表名/列名、grant 名、保护集字样；不给出任何数值或
  部分猜测；
- 不绕过：不查询原始 Schema、不猜测未在授权上下文出现的标识符。

### 4.3 读路径缺口（窄修复原则）

若机械链或冒烟发现授权语义不足以生成 SQL（如某口径字段读取面缺失），只修最窄失败层
（如 R3.0-003 detail 模板补一列投影），**不新增任何领域专属平台概念**（CLAUDE.md 边界）；
修复需在测试计划轮次记录中登记。

### 4.4 已记录边界（不修，不判 FAIL）

- 适配器只读兜底可被拥有写权限的数据库账户绕过（DSN 由运行环境治理）；
- 适配器不限行数/时长（资源配额属暂不细化）；
- SQL 文本质量不设静态检查门（AST/沙箱属暂不细化）。

### 4.5 平台/参考本体边界

适配器与冒烟驱动是通用机械件；全部领域名称只出现在 fixture、问句与断言；产品代码
（`backend/app/`）零改动即结构上满足边界（grep 门仍执行，见测试计划 F 组）。

## 5. 发布影响

- 预期**零产品代码改动、零 migration**（`uv run alembic current` 保持 `0032`）；仅新增
  repo-local 脚本与 `backend/tests/` 测试文件。
- 完成门：`cd backend && uv run pytest` 全绿；服务健康检查照常（冒烟依赖运行中的
  backend/MCP）；装载器执行一次装载 `industrial_service_v3`。
- 回滚：删除新增脚本与测试文件即回滚；装载的 schema 由装载器自身 guard 管理。

## 6. 验收标准（详见共享测试计划）

| ID | 标准 |
| --- | --- |
| A1 | 适配器合同：stdin/stdout JSON 形状、退出码、`config_error`/`input_error`/`database_error` 分类各有正反用例 |
| A2 | 连接级只读：写语句（含 DDL、WRITE 型 CTE）被 PostgreSQL 拒绝且数据零变更；只读查询不受影响 |
| A3 | 机械授权链（持权主体）：从授权读取面机械恢复口径并推导 SQL，经适配器执行，结果与独立基准一致；SQL 标识符全部有授权出处 |
| A4 | 机械授权链（无权主体）：必需资源缺失即终止于无法确认终态，输出不含任何受保护知识与泄露子串 |
| A5 | 冒烟 3–5 轮全部按 §3.5 判定通过并留档转录（含无权轮无法确认、缺口轮无原始 Schema 回退） |
| A6 | fixture seeding 批次落成之后的消费链与冒烟期间未发生 modeling start / Build Session / Batch（账面零建模 attempt 消耗；seeding 批次 ID 为登记基线） |
| A7 | 生产替换边界在适配器文件头与本文档成文；验收结论未宣称业务数据安全 |
| A8 | `cd backend && uv run pytest` 全量通过；R3.0-003/R3.0-004 既有套件零回归 |

## 7. 当前最小实现范围 vs 未来产品化

**当前最小**：§3.1 三部件 + §3.6 数据复用 + 测试计划全套。
**未来产品化（不得静默晋升）**：Connector 框架与数据源注册、行列/租户策略、SQL 治理
（AST/沙箱/配额/审计）、NL2SQL prompt 工程、Consumer Agent 常驻服务化、管理 UI。

## 8. 假设（错误则需重设计）

1. **R3.0-003 冻结的读取面足以承载 SQL 生成**：四类 detail 模板 `detail_fields` +
   context:query 候选 `data` 能机械闭合 fixture 问句所需全部口径。注意分工：context:query
   的 metric 候选 `data` 只携带 `grain/time_field/measure/aggregation/filters`，**不含**
   `valueExpression`；`valueExpression` 经 `metric-detail` 模板 `detail_fields` 精确读取
   取得（§3.3 六步链仍闭合）。若任一口径字段在授权读取面不可得且无法窄修复，机械链与
   问句集需重设计。
2. **冒烟运行时可按主体隔离并通过 MCP 消费**：MCP 进程以 `ONTOLOGY_MCP_API_KEY` 绑定单主体
   （双 key = 双进程/重启切换），所选 LLM Agent 运行时能把 Agent 的语义访问限制为平台 MCP
   读工具、把适配器限制为 shell 调用，且转录可完整留档。若工具面无法收窄或转录不可得，
   冒烟判定方式需重设计。
3. **fixture 重定位不算新场景内容**：把 R3.0-003 fixture 的表/列名改指
   `industrial_service_v3` 真实表被视为对既有 fixture 的调整（满足"零新场景内容"约束）。
   若被裁定为新增场景内容，数据计划需重设计。

## 附录 A 技术要点（文件级，非主线）

| 文件 | 改动 |
| --- | --- |
| `scripts/r3-0-005/sql_exec_adapter.py` | 新增：psycopg 单文件脚本；`R3005_SQL_ADAPTER_DSN` + `default_transaction_read_only=on`；stdin/stdout JSON 合同（§3.2）；文件头成文生产替换边界与"非策略引擎"声明 |
| `scripts/r3-0-005/consumer_smoke.py` | 新增：按轮次（问句 × 主体 key）启动 LLM Agent 运行时（MCP 语义读工具 + 适配器 shell 调用），落盘转录到 `docs/delivery/evidence/2026-08-27-r3-0-005/smoke/`；运行时选型（复用 `modeling_team/protocol_mcp_launch.py` 先例或独立驱动）实现期定，合同不变 |
| `backend/tests/test_r3005_sql_exec_adapter.py` | 新增：A1/A2（subprocess 驱动脚本；DSN 未设时 skip，先例 `RUN_OXIGRAPH_SPARQL_RUNNER_TESTS` 门控） |
| `backend/tests/test_r3005_authorized_sql_chain.py` | 新增：A3/A4（fixture 项目 + 双 key + 进程内 TestClient HTTP 读面（真实 store，`RUN_OXIGRAPH_SPARQL_RUNNER_TESTS` 门控）→ §3.4 机械推导 → 适配器执行 → 基准比对；含无法确认终态与无泄露断言；fixture 经 `KEY_MODEL` + Modeling Batch seeding） |
| `backend/app/` | 预期零改动；仅当读路径缺口触发 §4.3 窄修复时按最小 diff 登记 |
