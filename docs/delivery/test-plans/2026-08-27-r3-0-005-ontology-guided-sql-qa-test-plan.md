# R3.0-005 Ontology 引导的 SQL 问数链路 — 共享测试计划

- 日期：2026-08-27
- 状态：plan review: **PASS**（第一轮 REVISE 两项 High——H-1 fixture 写入路径与 F6
  零 Batch 矛盾、H-2 机械链测试依赖运行中 backend 且无可用性门控；修订为 Batch seeding
  + F6 核对范围收窄至 seeding 之后、进程内 TestClient + 真实 store + 既有门控 skip，
  窄幅复审 PASS。附注采纳：`valueExpression` 经 `metric-detail` 模板取得、不在
  context:query 候选 `data` 中）。待实现后由开发者自测；`requirement_tester` 在稳定状态
  独立复核并把轮次追加到本文
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
   `industrial_service_v3` 真实列一一对应，含 WorkOrder 上的 `repairDuration` 派生属性与
   `valueExpression` 文本）；TableMapping ×5（`work_orders`/`incidents`/`assets`/
   `equipment_models`/`spare_parts`，各含 business_key）；JoinMapping 链 ×3
   （work_orders↔incidents↔assets↔equipment_models）；EnumValueMeaning
   （statusCode 值 `RESOLVED` → 已完成工单）；MetricDefinition ×2——`METRIC_MTTR`
   （avg repairDuration，grain=设备型号属性，filters=statusCode eq RESOLVED）与
   `METRIC_PARTCOST`（avg standardCost，公共）。
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
- **S3 机械授权链（持权）**：`KEY_GRANT` 经进程内 TestClient HTTP 读面（detail 模板
  `entity` 精确读取 + context:query 定位）机械恢复 Q1/Q2 全部口径 → 按设计 §3.4 规则推导
  SQL → 适配器执行 →
  结果与基准一致；推导记录中每个标识符都有授权出处（出处不闭合即失败）。
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
     机械基准一致；回答说明业务口径（指标/聚合/粒度/过滤）；MCP 调用序列与设计 §3.3
     链路一致。
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
