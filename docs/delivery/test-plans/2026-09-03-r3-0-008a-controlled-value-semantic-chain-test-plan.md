# R3.0-008A 受控值 L1/L2/L3 表达合同与 `semanticValue` 映射链 — 共享测试计划

- 日期：2026-09-03
- 状态：待执行（开发者自测 → `requirement_tester` 独立验收）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-008A（含 2026-09-03 细化决策）
- 设计：`docs/delivery/designs/2026-09-03-r3-0-008a-controlled-value-semantic-chain-design.md`
- 执行者：开发者先自测；`requirement_tester` 独立复核（独立验收轮次结构见 §8）
- 测试位置：`backend/tests/`（pytest）+ `docs/delivery/evidence/2026-09-03-r3-0-008a/`（独立轮证据）
- 依赖基线：R3.0-001（装载器）、R3.0-003（映射合同，Round PASS）、R3.0-004（授权合同）、
  R3.0-005（消费链与适配器先例）全部已完成且其测试计划全绿；本计划在其上叠加，
  不修改其用例
- 真实运行口径：fixture 形态即本需求的"真实运行"载体（需求拆分决定；真实建模运行与
  联合验收归 R3.0-008B，其证据不得与本计划互替）

## 1. 测试边界

本计划只验收 R3.0-008A：

1. 命令面（create/update `semantic_value`）、G7 结构校验（存在/非映射类型/单值/悬挂）、
   读取面投影（context:query 映射候选 `data.semantic_value`、enum-meaning
   `detail_fields.semantic_value`）、Consumer 反向拼接闭环与授权无痕。
2. 领域风味名称（缺料、`PART_SHORTAGE` 等表/列/编码）只出现在 fixture、问句与断言；
   产品代码无领域分支（grep 门 F4）。
3. 不验收：`analyzed_not_materialized` 时点门与真实场景联合验收（R3.0-008B）、共性抽象
   （R3.0-009）、接口信息映射源（R3.0-010）、多源编码冲突模型、反向专用查询接口。
4. fixture seeding 之后（消费链与授权用例期间）不新建 Build Session / Modeling Batch /
   modeling start（F6 账面核对；seeding 批次 ID 为登记基线），不消耗建模 attempt 预算。
5. 设计 §4.2 已记录边界（`delete_class`/`delete_property` 不设悬挂门、同主体混用不可
   表达面、`businessMeaning` 不仲裁）不判 FAIL。
6. R3.0-005 适配器仅被复用（可选、DSN 门控）执行闭环 SQL；其自身合同不在本计划重验。

## 2. 稳定测试命令

从仓库根执行：

```bash
./scripts/load-industrial-service-v3-postgres.sh     # 装载数据基线（一次）
cd backend && uv sync --extra dev
cd backend && uv run pytest                          # 全量回归（完成门必需）
cd backend && uv run pytest tests/test_r3008a_semantic_value_integrity.py \
    tests/test_r3008a_controlled_value_chain.py       # 本需求新增（聚焦）
```

- 真实 store 用例沿 R3.0-005 先例：**进程内 FastAPI `TestClient` + 真实
  PostgreSQL/Oxigraph store**，`RUN_OXIGRAPH_SPARQL_RUNNER_TESTS` 门控，不可用时 skip
  并注明，不判 FAIL；不触碰运行中的 8001 共享运行时库/RDF 图。
- 闭环 SQL 执行（S5 可选增强）读取 `R3005_SQL_ADAPTER_DSN`；未设置时退化为 SQL 文本 +
  出处断言（不判 FAIL，注明）。
- 独立验收轮（§8）另需：`KEY_MODEL`（建 fixture）、`KEY_ADMIN`（org-admin）、read 双 key
  （见 §3.4）。

## 3. Fixture 设计

1. **PostgreSQL**：仅经既有安全装载器装载 `industrial_service_v3`（合同不变，不重验）。
2. **语义 fixture（pytest 内建，经 `KEY_MODEL` + Build Session + Modeling Batch
   dry-run → apply 提交，走真实产品写路径，seeding 批次 ID 登记为基线）**：
   项目 P、本体 `O_m`、默认图集；类 WorkOrder/DelayReason/SparePart 及属性（与真实列
   对应）；TableMapping ×3：`work_orders`（tm-wo，含 status → biz:status、
   work_order_number 列）、`work_order_delay_events`（tm-delay，含 cause_code →
   biz:delayCause）、`spare_parts`（tm-part，含 currency → biz:currency）；JoinMapping ×1：
   work_orders ↔ work_order_delay_events（work_order_id）。
   - **L3**：entity `biz:PartShortage`（`rdf:type biz:DelayReason`，`rdfs:label "缺料"`，
     另挂一条业务关系如 `biz:belongsTo biz:SupplyChainIssue` 证明 L3 参与关系召回）；
     `EnumValueMeaning` ×2 指向它：EM-CAUSE-PS（mappedProperty=biz:delayCause，
     enumValue=`PART_SHORTAGE`，businessMeaning=缺料，semanticValue=biz:PartShortage）与
     EM-STATUS-WP（mappedProperty=biz:status，enumValue=`WAITING_PARTS`，
     businessMeaning=缺料待料，semanticValue=biz:PartShortage）——**验收条件 2 的双指向**。
   - **L2**：EM-STATUS-RESOLVED（mappedProperty=biz:status，enumValue=`RESOLVED`，
     businessMeaning=已完成，无 semanticValue）。
   - **L1**：biz:currency 属性字面量直接经 tm-part 使用；**不建**任何 `EnumValueMeaning`
     或值节点。
3. **保护集与主体**：`PS_DELAY`（allowed_grants=["delay-visibility"]）成员 =
   `biz:PartShortage` IRI（仅此一个）；keys：`KEY_GRANT`（read + delay-visibility）、
   `KEY_NOGRANT`（read + 空 grants）、`KEY_MODEL`（model，建 fixture 用）、
   `KEY_ADMIN`（org-admin）。
4. **机械基准**：测试作者按 fixture 数据与装载器数据独立写死的期望值（或独立参考 SQL），
   与被测链路无共享代码；`cause_code='PART_SHORTAGE'` 的延期事件基准（WO-1001、WO-1008
   共 2 行）由独立参考 SQL 复核后写死。
5. **断链 fixture 变体**（代表问题断链矩阵，S5c）：在独立 fixture 项目或 apply 后追加
   update/delete 批次构造——(i) `update_enum_meaning` 清除 EM-CAUSE-PS 的
   semantic_value；(ii) 删除 tm-delay；(iii) 删除 EM-CAUSE-PS；(iv) 删除
   `businessMeaning`/`enumValue`（任一）；(v) 未授权主体（F1，不动 fixture）。
6. 每用例后清理 fixture 项目/本体/key。

## 4. 成功路径（S）

- **S1 L1 字面量链**：biz:currency → tm-part `column_mappings` 属性索引 →
  `SELECT … FROM industrial_service_v3.spare_parts WHERE currency='CNY'`（确认字面量直接
  使用）；RDF 断言：currency 无 `EnumValueMeaning`、无值节点（A1 L1 形态）。
- **S2 L2 枚举链**：「已完成」→ context:query（resource_types 含 mapping）→ EM-STATUS-
  RESOLVED 候选 data（mapped_property/enum_value/business_meaning，**无 semantic_value
  键**）→ 列定位 → SQL `WHERE status='RESOLVED'`；enum-meaning-detail 行 detail_fields
  同型。
- **S3 L3 投影与召回**：「缺料」→ context:query 同一响应内：resource 候选含
  `biz:PartShortage`（经 `rdfs:label` 召回，携带其业务关系可见性）；mapping 候选含
  EM-CAUSE-PS 与 EM-STATUS-WP，`data.semantic_value == biz:PartShortage` IRI；
  enum-meaning-list/detail 行 `detail_fields.semantic_value` 同值。
- **S4 双指向同 L3**：资源候选中类型为业务类（非 op:* 映射类型）且语义为"缺料"的业务
  节点**恰 1 个**（两个 `EnumValueMeaning` 仅以 mapping 候选形态出现，subjectTypes 含
  `op:EnumValueMeaning`）；机械链分别经 EM-CAUSE-PS → `cause_code='PART_SHORTAGE'` 与
  EM-STATUS-WP → `status='WAITING_PARTS'` 取得**各自**原始编码并生成两条不同过滤 SQL
  （A2）。
- **S5 代表问题闭环（A3）**：「查询因为缺料而延期的订单」机械链：S3 召回 →
  `semantic_value` 关联 → enum_value + mapped_property → 属性索引 + JoinMapping →
  `SELECT wo.work_order_number FROM industrial_service_v3.work_orders wo JOIN
  industrial_service_v3.work_order_delay_events de ON de.work_order_id=wo.work_order_id
  WHERE de.cause_code='PART_SHORTAGE'`；每个标识符有授权出处；设 `R3005_SQL_ADAPTER_DSN`
  时经适配器执行并与独立基准一致（WO-1001、WO-1008）。
  - **S5c 断链矩阵**：§3.5 变体 (i)–(iv) 各自使链路终止于无法确认终态
    （`UNCONFIRMABLE` 形态：无 SQL、无编码、无列名），且 (i) 清除后 EM-CAUSE-PS 仍可作为
    L2 正常工作（`business_meaning` 兜底），证明清除是降级不是破坏。
- **S6 升降级往返（A7）**：apply 后 `update_enum_meaning` 为 EM-STATUS-RESOLVED 增加
  `semantic_value`（L2→L3，dry-run/apply 通过，读取面出现投影）；再置 null 清除
  （L3→L2，读取面投影消失，枚举其余字段不变）。

## 5. 边界路径（B）

- **B1 G7-a 目标缺失**：create/update 指向合并视图中不存在的 IRI → dry-run 阻塞
  `invalid_resource_reference`（path=payload.semantic_value）；apply 同门。
- **B2 G7-a 跨拓扑**：目标 IRI 位于另一 Project/Ontology 的图（另一 fixture 本体中存在
  同名节点）→ 同 B1 拒绝形态（合并视图不可见即拒绝，不区分"不存在/别处存在"）。
- **B3 G7-b 非映射资源类型**：semantic_value 指向另一 `EnumValueMeaning` / `TableMapping`
  / `JoinMapping` / `MetricDefinition` / 指向自身 → 拒绝（覆盖「同一 RDF 主体混用」的
  可表达形态）。
- **B4 G7-c 多值**：载荷 `semantic_value` 为列表/非字符串 → 编译层 `InvalidCommandPayload`
  （dry-run finding）；另构造图内已有两个 `semanticValue` 对象的主体（测试内直写残留
  形态）→ G7 扫描拒绝。
- **B5 G7-d 悬挂保护**：批次仅含 `delete_entity` 删除 `biz:PartShortage` → 阻塞
  `semantic_value_dangling` 并归属到该删除项；同批「删 L3 + 建指向它的枚举」同拒；
  删除未被指向的实体不受影响（对称 G3 的无关删除放行先例）。
- **B6 零猜测物化（A4 末项）**：fixture 全量 apply 后，图内每个 `EnumValueMeaning` 与
  entity 均可追溯到显式批内命令（逐 subject 对照 seeding 批次 plan）；对"编码未确认"
  的候选值（fixture 中只出现在 note 文本里的编码）断言 RDF 中不存在对应
  `EnumValueMeaning` / L3 节点；命令面不存在自动创建路径（白名单外字段拒绝复核）。
- **B7 G2 视图守恒（计划评审 Round 2 复审备注补）**：`create_enum_meaning` 的
  `property_iri` 指向 data graph 中的实体 IRI 仍被既有 G2 拒绝（证明 G7 双图视图未
  扩散进 G2–G6 的查询口径）。

## 6. 失败路径（F，若发生即 FAIL）

- **F1 未授权 L3 无痕（A5）**：`KEY_NOGRANT` 下：EM-CAUSE-PS/EM-STATUS-WP 的 mapping
  候选与 enum-meaning 行整条隐藏；`biz:PartShortage` resource 候选隐藏；S5 链路终止于
  无法确认终态；终态输出与「从未建过该 L3」的对照 fixture 输出不可区分（逐字节或语义
  等价断言）。
- **F2 无泄露**：F1 终态与响应内不含 `biz:PartShortage`/缺料/`delay-visibility`/
  `protection`/`PS_DELAY` 等子串（EM-STATUS-RESOLVED 等未保护资源照常可见——无痕子集
  合同）。
- **F3 授权合同回归**：R3.0-004 套件（`test_semantic_access_*`、
  `test_semantic_protection_sets.py`）任一失败。
- **F4 边界守恒（grep 门）**：产品代码增量限于设计附录 A 五文件；新增源码无
  `缺料`/`PART_SHORTAGE`/`WAITING_PARTS`/fixture 表列名等领域字符串；无新增 API 路由/
  MCP 工具/migration。
- **F5 RDF 未复制业务行（A6）**：fixture 本体图中不存在 `work_orders`/`incidents`/
  `spare_parts` 行级主体（按行 IRI/主键字面量断言，R3.0-003 既有断言形态不回归）。
- **F6 建模零消耗**：seeding 批次落成之后的消费链/授权用例期间，平台无新建 Build
  Session / Modeling Batch / modeling start（账面核对；断链变体 (i)/(ii)/(iii)/(iv) 的
  追加 update/delete 属 S5c 显式登记的 fixture 变体批次，计入基线登记，不计违规）。

## 7. 回归（R）

- **R1 全量回归**：`cd backend && uv run pytest` 全绿（默认门控与
  `RUN_OXIGRAPH_SPARQL_RUNNER_TESTS` 门控各跑一次，skip 干净无假失败）。
- **R2 依赖套件保持绿**：R3.0-003（`test_modeling_batches_relational_mapping.py`——含
  G5 用例 466/493、G2/G3/G6——`test_semantic_command_compiler_r3003.py`）、R3.0-004、
  R3.0-005（`test_r3005_authorized_sql_chain.py`、`test_r3005_sql_exec_adapter.py`）、
  R3.0-007 相关文件零回归。
- **R3 装载器幂等**：测试完成后重跑装载器恢复 PostgreSQL 基线。

## 8. 真实运行与独立验收轮次（L；fixture 形态即本需求"真实运行"载体）

1. **L1 健康与基线**：`ontology-platform.service` active；backend `/api/health` 200、
   frontend 5173 200；`alembic current` 仍 `0032`；`industrial_service_v3` 已装载；
   G7/投影代码已合入并重启。
2. **L2 独立验收轮（`requirement_tester` 执行，不创建也不延续其评估的运行）**：
   - 用 `KEY_ADMIN` 建独立 fixture 项目/本体/graph set，`KEY_MODEL` 经真实 Build Session
     + Modeling Batch（dry-run → apply）落 §3 fixture，登记 seeding 批次 ID 为本轮基线；
     建 `PS_DELAY` 与双 read key；
   - 经真实读面（进程内 TestClient + 真实 store，或运行中 8001 的 HTTP 面——测试者择一
     并登记）活体复证：S3/S4/S5（含适配器执行与独立基准比对，DSN 可用时）、S6、
     B1–B6、F1/F2/F5（未授权与无泄露形态）、F6 账面核对；
   - 判定与证据落 `docs/delivery/evidence/2026-09-03-r3-0-008a/`（批次 ID、关键响应
     摘录、SQL 与基准、终态对照），转录不含 key 明文。
3. **L3 轮次记录**：§轮次记录登记每轮判定、缺陷与修复（含窄修复登记——若读取面/校验
   发现缺口，按 R3.0-005 §4.3 先例只修最窄失败层并在设计文档登记）。
   **轮次结构**：开发者自测轮（全 S/B/F/R + 修缺陷）→ 独立测试 Round 1（全量复证）→
   如 FAIL，窄修复后 Round 2 复测失败项 + 受影响面；独立测试证据与开发者自测证据分别
   留档，不得互相替代或追溯解释为 R3.0-008B 验收。

## 9. 清理

1. 撤销全部 fixture key；删除 fixture 项目/本体/graph set（保护集随项目级联；Oxigraph
   残留图复核为零，R3.0-005 Round 2 先例）。
2. 删除临时探针与含 key 的临时文件；独立轮证据留存（脱 key）。
3. 可选：重跑装载器恢复 PostgreSQL 基线（R3）。

## 10. 判定规则与完成门

- **PASS**：S1–S6、B1–B6、F1–F6、R1–R3、L1–L3 全部通过；设计 §6 A1–A8 全部有证据；
  R3.0-008A 需求状态更新；未宣称 R3.0-008B/R3.0-010/v3.0 完成。
- **FAIL**：G7 任一拒绝路径放行（B1–B5）；未授权 L3 泄露或终态可区分（F1/F2）；
  授权合同回归（F3）；边界守恒破坏（F4）；RDF 出现业务行（F5）；建模 attempt 被消耗
  （F6 账面外新建且未登记）；全量 pytest 失败。
- **BLOCKED**：仅用于 PostgreSQL/Oxigraph/系统服务不可用等外部条件。
- 完成后由主 agent 收口：更新需求状态与文档信息区链接；R3.0-008B、R3.0-010 保持待细化/
  待验收。
- 独立测试不创建也不延续其评估的运行，不改动已保留证据。

## 轮次记录

（开发者自测与独立测试轮次由执行者追加，不得改写历史轮次。）
