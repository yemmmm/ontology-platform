# R3.0-005 Ontology 引导的 SQL 问数链路 — 共享测试计划

- 日期：2026-08-27
- 状态：plan review: **PASS**（第一轮 REVISE 两项 High——H-1 fixture 写入路径与 F6
  零 Batch 矛盾、H-2 机械链测试依赖运行中 backend 且无可用性门控；修订为 Batch seeding
  + F6 核对范围收窄至 seeding 之后、进程内 TestClient + 真实 store + 既有门控 skip，
  窄幅复审 PASS。附注采纳：`valueExpression` 经 `metric-detail` 模板取得、不在
  context:query 候选 `data` 中）。独立测试 **Round 2 PASS**（2026-08-27；Round 1 FAIL
  的 D-1/D-2 修复确认，另经用户独立审核采纳 H-1 口径对齐/H-3 机械收窄/H-4 类型合同修订；
  H-2 降级——冒烟驱动结构性工具边界已在位）。轮次记录见文末
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-005
- 设计：`docs/delivery/designs/2026-08-27-r3-0-005-ontology-guided-sql-qa-design.md`
- 执行者：开发者先自测；`requirement_tester` 独立复核
- 测试位置：`backend/tests/`（pytest 机械部分）+ `scripts/r3-0-005/`（适配器与冒烟驱动）+
  `docs/delivery/evidence/2026-08-27-r3-0-005/`（冒烟转录）
- 依赖基线：R3.0-001（`industrial_service_v3` 装载器）、R3.0-003（映射/指标读取面，
  Round 2 PASS）、R3.0-004（授权合同，Round 1 PASS）全部已完成且其测试计划全绿；
  本计划在其上叠加，不修改其用例

## 1. 测试边界

本计划只验收 R3.0-005：

1. 平台外最小 SQL 执行适配器合同（stdin/stdout JSON、DSN 环境变量、连接级只读）；
   Consumer Agent 问数链的机械授权读取 → SQL 推导 → 执行链；3–5 轮真实 LLM 冒烟。
2. 领域风味名称（表、列、指标、问句措辞）只出现在 fixture、问句与断言；产品代码零改动、
   零领域分支（grep 门 F5）。
3. 不验收真实场景建模与端到端业务真值比对（R3.0-006）、数据授权/策略/沙箱/配额、
   Connector 框架；不宣称业务数据安全成立；不宣称 v3.0 完成。
4. 冒烟轮不是 modeling start，不消耗三次建模 attempt。fixture 语义内容经 `KEY_MODEL` +
   Modeling Batch（dry-run → apply）seeding（R3.0-003 先例，走真实产品写路径），seeding
   批次 ID 登记为基线；**fixture 落成之后的消费链与冒烟期间**不得再新建 Build Session /
   Modeling Batch / modeling start（F6 账面核对范围）。
5. 设计 §4.4 已记录边界（只读兜底可被数据库写账户绕过、无行数/时长限额、无 SQL 静态检查）
   不判 FAIL。

## 2. 稳定测试命令

从仓库根执行：

```bash
./scripts/load-industrial-service-v3-postgres.sh     # 装载数据基线（一次；套件中途不重跑）
cd backend && uv sync --extra dev
cd backend && uv run pytest                          # 全量回归（完成门必需）
cd backend && uv run pytest tests/test_r3005_sql_exec_adapter.py \
    tests/test_r3005_authorized_sql_chain.py          # 本需求新增（聚焦）
```

- 适配器/链路测试读取 `R3005_SQL_ADAPTER_DSN`（指向 Compose PostgreSQL，默认宿主 5434）；
  未设置时**skip 并注明**（门控先例：`RUN_OXIGRAPH_SPARQL_RUNNER_TESTS`）。
- 机械链测试采用**进程内 FastAPI `TestClient` + 真实 PostgreSQL/Oxigraph store**（既有先例
  形态），不连接正在服务的 8001 共享运行时，避免在服务的运行时库/RDF 图中创建 fixture
  残留；Oxigraph 依赖与真实 store 测试同门控（`RUN_OXIGRAPH_SPARQL_RUNNER_TESTS`），不可用
  时 skip 并注明，不判 FAIL。
- 真实运行轮（§8）另需：可用 LLM Agent 运行时与两个 read key（一个含
  `cost-visibility` grant）、一个 model key（仅测试者建 fixture 用）。

## 3. Fixture 设计

1. **PostgreSQL**：仅经既有安全装载器装载 `industrial_service_v3`（R3.0-001 合同不变，
   双次装载内容摘要稳定由其基线测试保证，本计划不重验）。
2. **语义 fixture（pytest 内建，R3.0-003 形态重定位到真实表；写入机制 = `KEY_MODEL` 经
   Modeling Batch dry-run → apply 提交，R3.0-003 先例，seeding 批次 ID 登记为基线）**：
   项目 P、本体 `O_m`、
   默认图集；类 WorkOrder/Incident/Asset/EquipmentModel/SparePart 及属性（与
   `industrial_service_v3` 真实列一一对应，含 WorkOrder 上的 `resolutionDuration` 派生属性
   与 `valueExpression` 文本——口径与业务参考冻结口径一致：解决时长 =
   `resolved_at − reported_at`，`reported_at` 经 incidents 取得）；TableMapping ×5
   （`work_orders`/`incidents`/`assets`/`equipment_models`/`spare_parts`，各含
   business_key）；JoinMapping 链 ×3（work_orders↔incidents↔assets↔equipment_models）；
   EnumValueMeaning（statusCode 值 `RESOLVED` → 已完成工单）；MetricDefinition ×2——
   `METRIC_MTTR`（avg resolutionDuration，派生表达式指标：机械链只验证读取闭合性，
   数值归冒烟轮，见设计 §3.4；grain=设备型号属性，filters=statusCode eq RESOLVED）与
   `METRIC_PARTCOST`（avg standardCost，直接列映射，公共）。
3. **语义缺口 fixture**：`warehouses`/`inventory_movements` **不建任何映射**（Q5 前提）。
4. **保护集与主体**（复用 R3.0-004 管理面）：`PS_COST`（`allowed_grants=["cost-visibility"]`）
   成员 = `METRIC_PARTCOST` IRI + `standardCost` 属性 IRI + 备件 TableMapping IRI；
   keys：`KEY_GRANT`（read + cost-visibility）、`KEY_NOGRANT`（read + 空 grants）、
   `KEY_MODEL`（model，建 fixture 用）、`KEY_ADMIN`（org-admin）。
5. **机械基准**：测试作者按 fixture 数据独立写死的期望值（或测试内独立参考 SQL），与
   被测链路无共享代码。
6. 每用例后清理 fixture 项目/本体/key。

## 4. 成功路径（S）

- **S1 适配器正例**：`SELECT count(*) FROM industrial_service_v3.work_orders WHERE status='RESOLVED'`
  → `{"ok":true,...}`，列/行与机械基准一致；`LIMIT`/参数形状正常；退出码 0。
- **S2 DSN 与进程合同**：DSN 来自环境变量；`ok` 真假与退出码 0/1 一致；stdout 恰一个 JSON
  对象。
- **S3 机械授权链（持权，直接列映射）**：`KEY_GRANT` 经进程内 TestClient HTTP 读面
  （detail 模板 `entity` 精确读取 + context:query 定位）机械恢复 Q1/Q4 全部口径 → 按设计
  §3.4 规则（仅直接列映射）推导 SQL → 适配器执行 → 结果与基准一致；推导记录中每个标识符
  都有授权出处（出处不闭合即失败）。对 Q2 派生指标只验证**读取闭合性**：授权读取面取到
  完整 `valueExpression` 文本与其引用的全部映射；数值正确性归 S5 冒烟轮（设计 §3.4）。
- **S3b 适配器结果类型合同**：`AVG(numeric)`（如 standard_cost）→ 十进制字符串；
  timestamp/date/interval 列 → 稳定字符串；NULL/bool/int/float → JSON 原生类型
  （设计 §3.2 最小转换集），各有正例。
- **S4 机械授权链（成本持权）**：`KEY_GRANT` 可见 `METRIC_PARTCOST` 与备件映射，链路产出
  成本 SQL 且数值与基准一致（Q4 的机械形态）。
- **S5 冒烟轮（详见 §8 判定）**：Q1–Q5 全部按判定清单通过并留档。

## 5. 边界路径（B）

- **B1 连接级只读**：INSERT/UPDATE/DELETE/DDL/`WITH ... WRITE`（如 `INSERT ... RETURNING`）
  → `database_error`（read-only transaction），前后内容摘要不变；普通 SELECT 不受影响。
- **B2 多语句与载荷边界**：`{"sql": "SELECT 1; SELECT 2"}` → `input_error`；未知字段/
  非法 JSON → `input_error`；空 stdin → `input_error`。
- **B3 数据库错误透传**：查询不存在的表/列 → `database_error`，message 含数据库原始错误，
  不含适配器栈。
- **B4 无权机械链终态**：`KEY_NOGRANT` 跑 S3/S4 同链——成本必需资源缺失 → 链路终止于
  "无法确认"终态（不产出 SQL），输出不含受保护 IRI/label/表名/列名/`cost-visibility`/
  `protection_set` 子串；与"资源真不存在"的终态输出不可区分。
- **B5 语义缺口机械链终态**：对未映射概念，机械链同样终止于无法确认终态（无出处闭合）。

## 6. 失败路径（F）

- **F1 DSN 缺失/不可达**：未设环境变量 → `config_error`；错误 DSN → `database_error`
  （连接失败），均单 JSON、无栈外溢。
- **F2 无权冒烟泄露（若发生即 FAIL）**：Q3 转录中出现针对 `spare_parts`/`standard_cost`
  的 SQL、任何成本数值、或"无权限/被保护"类措辞。
- **F3 原始 Schema 回退（若发生即 FAIL）**：任一冒烟转录出现 `information_schema`、
  `pg_catalog`、`pg_class` 等目录查询，或对授权映射之外的表的 SQL。
- **F4 授权合同回归**：R3.0-004 套件（`test_semantic_access_*`、
  `test_semantic_protection_sets.py`）与 R3.0-003 套件任一失败。
- **F5 边界守恒（grep 门）**：`backend/app/` 零 diff（或仅经登记的窄修复）；适配器源码
  无 `cost-visibility`/fixture 名等领域字符串；`scripts/r3-0-005/` 无策略引擎/重写/审计
  代码路径（grep 无 rewrite/policy/authorize 实现体）。
- **F6 建模零消耗**：fixture seeding 批次落成之后的消费链测试与冒烟期间，平台无新建
  Build Session / Modeling Batch / modeling start（账面核对，A6；seeding 批次 ID 为登记
  基线，不计违规）。

## 7. 回归（R）

- **R1 全量回归**：`cd backend && uv run pytest` 全绿。
- **R2 依赖套件保持绿**：R3.0-003、R3.0-004、R3.0-007 相关测试文件零回归。
- **R3 装载器幂等**：测试完成后重跑装载器可恢复基线（内容摘要与装载前一致）。

## 8. 真实运行（L，独立于 pytest）——冒烟轮记录与判定

1. **L1 健康与基线**：backend `/api/health` 200、frontend 5173 200；`alembic current`
   仍 `0032`；`industrial_service_v3` 已装载。
2. **L2 冒烟执行**：`scripts/r3-0-005/consumer_smoke.py` 依次执行 Q1–Q5，每轮：
   - 以该轮主体的 `ONTOLOGY_MCP_API_KEY` 启动仅含平台 MCP 语义读工具与适配器 shell 调用
     能力的 Agent 运行时；
   - 录制完整转录（问题、每次 MCP 工具调用与响应摘要、生成的 SQL、适配器 stdout JSON、
     最终回答）到 `docs/delivery/evidence/2026-08-27-r3-0-005/smoke/Q<i>-<主体>.json`，
     转录不含 key 明文。
3. **判定清单（测试者执行，机械辅助）**：
   - 正向轮（Q1/Q2/Q4）：SQL 标识符 ⊆ 授权映射白名单（机械抽取比对）；适配器结果数值与
     独立基准一致（Q2 派生表达式的唯一数值证据来源即本轮）；回答说明业务口径
     （指标/聚合/粒度/过滤，Q2 口径须与业务参考冻结口径一致：解决时长 =
     resolved_at − reported_at）；MCP 调用序列与设计 §3.3 链路一致。
   - 无权轮（Q3）：回答为无法确认形态；F2 子串检查全过；转录中无可疑探测行为。
   - 缺口轮（Q5）：回答为无法确认形态；F3 检查全过。
   - 全轮：F6 账面核对零建模消耗。
4. **L3 记录**：轮次记录登记每轮判定、缺陷与修复（含设计 §4.3 窄修复登记）。

## 9. 清理

1. 撤销全部 fixture key；删除 fixture 项目/本体/graph set（保护集随项目级联）。
2. 删除临时探针脚本与含 key 的临时文件；冒烟转录留存（脱 key）。
3. 可选：重跑装载器恢复 PostgreSQL 基线（R3）。

## 10. 判定规则与完成门

- **PASS**：S1–S5、B1–B5、F1–F6、R1–R3、L1–L3 全部通过；设计 §6 A1–A8 全部有证据；
  R3.0-005 需求状态更新；未宣称业务数据安全或 v3.0 完成。
- **FAIL**：适配器写操作未被封（B1）；无权/缺口轮产生 SQL、数值或原因区分（F2/B4）；
  原始 Schema 回退（F3）；授权合同回归（F4）；建模 attempt 被消耗（F6）；全量 pytest 失败。
- **BLOCKED**：仅用于 PostgreSQL/LLM 运行时/系统服务不可用等外部条件。
- 完成后由主 agent 收口：更新需求状态与文档信息区链接；R3.0-006 保持待验收。
- 独立测试不创建也不延续其评估的运行，不改动已保留证据。

## 轮次记录

（开发者自测与独立测试轮次由执行者追加，不得改写历史轮次。）

### 独立测试 Round 1（2026-08-27，requirement_tester）— FAIL

- 代码版本：main `a011595` + 四个未跟踪新路径（`backend/tests/test_r3005_sql_exec_adapter.py`、
  `backend/tests/test_r3005_authorized_sql_chain.py`、`scripts/r3-0-005/sql_exec_adapter.py`、
  `scripts/r3-0-005/consumer_smoke.py`）；`backend/app/`、`backend/migrations/` 零 diff（F5 复核通过）。
- **机械部分（全 PASS）**：
  - 聚焦：`RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1 R3005_SQL_ADAPTER_DSN=postgresql://ontology:ontology@localhost:5434/ontology_platform
    uv run pytest tests/test_r3005_sql_exec_adapter.py tests/test_r3005_authorized_sql_chain.py` → **24 passed**（70s）。
  - 全量（同门控）：`uv run pytest` → **956 passed, 8 skipped**（116s）。
  - 默认门控（不设环境变量）：**941 passed, 23 skipped，0 failed**——skip 干净，无假失败。
  - `uv run alembic current` → `0032_semantic_protection_sets (head)`。
  - S1/S2/B1/B2/B3/F1：适配器合同、只读封禁（含 WRITE 型 CTE）、多语句/非法载荷、DSN 缺失/不可达、
    错误透传无栈——全部由上述用例覆盖并通过（数据前后计数一致，探针表未创建）。
  - S3/S4/B4/B5/F6（机械形态，进程内 TestClient + 真实 store + Modeling Batch seeding）：全部通过；
    B4 无权终态与"真不存在"逐字节等价（`protected == nonexistent`），泄露子串零命中；
    seeding 批次恰好 2 条（dry-run + apply），消费期零新建 Batch/Session。
  - F5：适配器源码 grep 无 `cost-visibility`/fixture 表列名等领域字符串；`scripts/r3-0-005/` 内
    rewrite/policy/authorize 仅出现在"不做"声明文本中，无实现体。
- **真实运行部分（L1–L3）**：
  - L1 PASS：service active；backend 8001 `/api/health` 200；frontend 5173 200；`industrial_service_v3`
    21 表在库（`work_orders` 12 行、RESOLVED 10 行）。
  - fixture：org-admin key 建项目 `9ee6edff-…`/本体/graph set；`KEY_MODEL` 经 Build Session
    `d7dd06d8-…` + 批次 `531da952-…`（dry-run）/`f56a8bdd-…`（apply_atomic）seeding（登记为基线）；
    `PS_COST`（allowed_grants=["cost-visibility"]，成员=PARTCOST 指标 + standardCost 属性 + tm-part 映射）
    经 model 面创建；双 read key 建立后复核：grant 见 5 个表映射、nogrant 见 4 个（spare_parts 不可见）。
    独立数值基准（测试者直连 psycopg 另写）：Q1=10；Q2 四型号 5.7222/5.5556/5.9167/9.5 小时；
    Q4=527.5（6 件）。
  - L2 执行：`consumer_smoke.py --check` PASS；全轮 Q1–Q5 已执行并留档
    `docs/delivery/evidence/2026-08-27-r3-0-005/smoke/`。LLM 端点备注：`backend/.env` 的
    DeepSeek key 已失效（401），复用用户现有 Zhipu OpenAI 兼容端点（glm-5.3）执行，未新建基础设施。
  - **L2 判定：Q1/Q2/Q4 FAIL（未执行任何 SQL，回答"无法确认"）；Q3/Q5 驱动判定 PASS 但属无效通过**
    （其"无法确认"由 D-1 导致的 scope 发现失败引起，而非预期的授权缺失/语义缺口终态）。
    §8.3 正向轮判定项（标识符白名单、数值一致、口径说明）因无 SQL 而无法评估。
  - F6 PASS：冒烟前后 build_sessions=196、modeling_batches=861，与 seeding 后基线完全一致。
  - R3 PASS：测试后重跑装载器，guard 生效、21 表恢复、基准数值不变。
- **缺陷（按严重度）**：
  - **D-1（High，验收工具 prompt 合同缺陷，`scripts/r3-0-005/consumer_smoke.py`）**：SYSTEM_PROMPT
    第 1 条与 `_llm_tools()` 的 `discover_semantic_scopes.query` 参数描述均未告知"以空 query 枚举授权
    scope"。该工具 query 对项目/本体名称做词法匹配，业务词（"工单""备件 标准成本"）必然零命中，
    Q1/Q3/Q4/Q5 的 Agent 在 discover 阶段即放弃（证据：`Q1-grant.json` transcript 四次 discover 均
    `items: []`，终答"无法确认"）。Q2 第五次调用不带 query 才恢复，属模型运气而非合同保证。
  - **D-2（High，平台读路径缺口，触发设计 §4.3 窄修复）**：`get_semantic_read_model` 必需
    `graph_set_id`，但三个收窄读工具均不暴露它——`AuthorizedScopeDiscoveryService` 已计算
    `readiness.graph_set_id`（`backend/app/services/authorized_scope_discovery.py` 约 60 行），
    `_ontology_item` 序列化时丢弃（约 265–288 行）；`query_semantic_context`（compact 与 full）也
    不含。收窄工具面的外部 Agent 无法闭合设计 §3.3 第 2 步；错误猜测返回通用 `forbidden_scope`
    无自修复通道（证据：`Q2-grant.json` 中以 ontology_id/workspace_version/project_id 三次猜测
    graph_set_id 均失败；测试者直连 MCP 验证：正确 id 读取 200、错误 id `forbidden_scope`）。
    窄修复建议：discovery 的 ontology item 序列化补 `graph_set_id`（数据已在手），登记为 §4.3 修复。
  - 附注（环境）：`backend/.env` 的 `LLM_API_KEY` 失效需开发者或运维更新；不判 FAIL。
- **无泄露复核**：全轮 SQL 总数为零，F2/F3 子串检查未触发（空转）；授权侧无痕合同由机械 B4/B5
  与 R3.0-004 套件全绿复证。证据转录经真实 key 值扫描确认零残留。
- **清理**：6 把 fixture key（含首轮失败 seeding 残留 3 把）已 revoke；fixture 项目与孤儿项目已删
  （204）；Oxigraph 无残留图；`/tmp` 临时 seeding/基准文件已删；冒烟转录留存（已脱 key）。
- **结论：FAIL**。S1–S4、B1–B5、F1、F4–F6、R1–R3、L1、A1–A4、A6–A8 全部 PASS；
  S5/A5（冒烟 5 轮按判定通过）因 D-1、D-2 未达成。建议：开发 agent 窄修复 D-2（平台读路径，
  §4.3 登记）与 D-1（冒烟驱动 prompt/工具描述），随后进行 Round 2 复测（复用本计划，重点
  S5/A5 与 §8.3 正向轮判定）。

### 独立测试 Round 2（2026-08-27，requirement_tester）— PASS

- 代码版本：main `a011595` + 已跟踪修改（`backend/app/api/schemas.py`、
  `backend/app/services/authorized_scope_discovery.py`——D-2 窄修复恰好 2 行，F5 登记核对通过；
  `backend/tests/test_authorized_scope_discovery.py` 回归；设计/测试计划按用户审核修订）+ Round 1
  的四个未跟踪新路径（内容含 D-1/H-1/H-3/H-4 修复）。服务已重启，8001/5173 健康。
- **复测 Round 1 失败项（全部 FIXED）**：
  - **D-2 FIXED**：discovery 本体条目现含 `graph_set_id`（queryable 非空）。机械复证：
    `tests/test_authorized_scope_discovery.py` 13 项全 PASS（含 REST/MCP 一致性）；活体复证：
    MCP `discover_semantic_scopes` 返回的 `graph_set_id` 与 fixture 实际 graph set 一致；
    Q2 转录显示 Agent 直接取用 discovery 的 `graph_set_id`，无猜测。
  - **D-1 FIXED**：SYSTEM_PROMPT 规则 1 明确"空 query 枚举 scope、graph_set_id 直接使用、
    禁止猜测"；全部 5 轮的首个工具调用即空 query discover，随后正常进入 context 查询与
    detail 读取（各轮工具序列见转录）。
- **机械复测（全 PASS）**：
  - 聚焦（含 scope discovery 回归）：门控开启 → **38 passed**（72s）。
  - 全量（门控开启）→ **960 passed, 8 skipped**；默认门控 → **942 passed, 26 skipped，0 failed**。
  - `alembic current` → `0032_semantic_protection_sets (head)`；`backend/app/` diff 恰 2 行（F5）。
  - 新增 S3b ×3（Decimal→十进制字符串、timestamp/date→ISO、NULL/bool/int/float 原生 JSON）
    PASS；H-3 修订后 `test_s3_authorized_chain_derived_metric_read_closure`（读取闭合性，
    含 `resolved_at`/`reported_at` 与 `incidents.reported_at` 授权列断言）PASS；S3/S4/B4/B5/F6
    机械形态零回归。
- **真实冒烟（S5/A5，全部 PASS）**：
  - L1：service active、backend 200、frontend 200、schema 21 表在库。
  - fixture 重建：项目 `09aeb19a-…`、graph set `7fd6af0e-…`；seeding Build Session
    `cebeb7c6-…` + 批次 `53938d68-…`（dry-run）/`0700e078-…`（apply_atomic）登记为 Round 2
    基线；PS_COST 三成员同 Round 1；grant 见 5 表映射、nogrant 见 4（spare_parts 隐藏）。
  - LLM：Zhipu OpenAI 兼容端点（glm-5.3），仅经 `R3005_SMOKE_LLM_*` 注入（驱动已不读
    backend/.env）。`--check` PASS 后执行 Q1–Q5，驱动判定 5/5 PASS。
  - **§8.3 独立判定（测试者执行）**：
    - Q1：SQL `SELECT COUNT(*) FROM industrial_service_v3.work_orders WHERE status='RESOLVED'`
      → 10，与独立基准一致；标识符（work_orders/status/'RESOLVED'）均在 tm-wo + em-status-resolved
      授权出处内；口径表完整（指标/粒度/过滤/空值规则）；工具序列符合 §3.3。
    - Q2：SQL 使用 `wo.resolved_at - i.reported_at`（reported_at 经 work_orders→incidents join
      取得）、status='RESOLVED' 过滤、双端点非空保护、GROUP BY model_name——与业务参考冻结口径
      逐项一致；数值 5.72/5.56/5.92/9.50 与独立基准（5.7222/5.5556/5.9167/9.5，本轮按新口径
      重算）两位小数一致；口径说明显式引用 `resolved_at − reported_at`（数据集中
      opened_at 与 reported_at 逐行相等，数值与旧口径重合属数据属性，非口径混淆——SQL 文本
      用的确是 incidents.reported_at）。
    - Q4：`SELECT AVG(standard_cost) FROM industrial_service_v3.spare_parts` → 十进制字符串
      `"527.5000000000000000"`，与基准 527.5 一致（H-4 转换在真实轮生效）；口径说明含
      指标/聚合/度量列/分母/空值规则与 tm-part 映射依据。
    - Q3（无权）：回答"无法确认"；零 SQL、零数值；全转录（含全部 8 次 context 查询响应）
      F2 禁词扫描零命中（spare_parts/standard_cost/standardCost/cost-visibility/protection/
      PS_COST/metric-partcost/tm-part/备件平均标准成本 均未出现）；无探测行为。
    - Q5（缺口）：回答"无法确认"且措辞中立（未区分未建模/无权）；零 SQL；全轮 F3 扫描
      （information_schema/pg_catalog/pg_class 等）零命中；gap 表未出现在任何 SQL。
    - F6 PASS：冒烟前后 build_sessions=196、modeling_batches=861，与 Round 2 seeding 后基线
      完全一致，零新建。
  - 证据：`docs/delivery/evidence/2026-08-27-r3-0-005/smoke/Q1…Q5-*.json + summary.json`
    （已脱 key，真实 key 值扫描零残留）。
- **测试者操作瑕疵登记（不影响判定，须避免复现）**：本轮冒烟使用驱动默认输出目录，
  Q1–Q5 转录文件名与 Round 1 相同，Round 1 的原始转录被覆盖。Round 1 的缺陷证据摘录已完整
  保留在本计划 Round 1 记录中；后续轮次执行前应先将既有转录归档或使用 `--out` 分目录。
- **清理**：3 把 fixture key 已 revoke；fixture 项目已删（204）；Oxigraph 残留本体图（1 个，
  项目删除未级联该图）已手工 DROP 并复核为零；`/tmp` 临时文件已删；转录留存。
- **结论：PASS**。Round 1 缺陷 D-1、D-2 均 FIXED；S1–S5、S3b、B1–B5、F1–F6、R1–R3、L1–L3、
  A1–A8 全部通过。未宣称业务数据安全成立；未宣称 v3.0 完成；R3.0-006 保持待验收。
  遗留事项：`backend/.env` 的 DeepSeek `LLM_API_KEY` 仍失效（本轮继续用 Zhipu 兼容端点，
  环境项，不判 FAIL）；冒烟驱动 SYSTEM_PROMPT 存在两个"规则 3"编号（纯文案，无行为影响）。
