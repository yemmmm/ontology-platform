# v3.0 工业售后服务场景准备与数据基线设计

- 日期：2026-08-22
- 状态：已实现；独立测试 T1～T5 PASS（2026-08-22）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-001
- 交付边界：仅准备文档、建模输入和 PostgreSQL 数据；不实现 R3.0-002～R3.0-006
- 共享测试计划：
  `docs/delivery/test-plans/2026-08-22-v3-0-industrial-service-scenario-preparation-test-plan.md`

## 后续架构边界说明（2026-08-25）

本设计及其 R3.0-001 验收结论保持不变。后续需求概要设计已补充于
`docs/delivery/designs/2026-08-25-v3-0-remaining-requirements-outline-design.md`。后续已确认：保护集是
Project 级平台控制面，可跨同一 Project 的多个 Ontology，不属于 Ontology 内容；本设计中关于
R3.0-002～R3.0-006 的未来方向如与该概要设计冲突，以 `requirements-v3.0.md` 和新概要设计为准。

## 1. 设计结果

本轮建立一个可以供后续真实建模使用、但不会提前替建模 Agent 作答的场景基线。交付物分为三个
严格隔离的层次：

1. **需求与业务真值层**：完整流程参考、隐藏规则、指标口径、保护受众示例和验收问题，放在场景输入树
   之外，供需求、实现、独立测试使用，不进入建模输入。
2. **建模输入层**：简短业务说明、有限术语、完整 PostgreSQL Schema 和代表性样例行。其信息足以
   发现概念和关系，但不足以确定全部业务含义，迫使后续建模流程通过用户访谈消除歧义。
3. **运行数据层**：与建模输入完全同源的 `schema.sql` 和 `sample-data.sql` 被实际装载到现有开发
   PostgreSQL 的独立 schema；不复制到 RDF，不侵入产品 migration。

该分层在本轮建立可审查的资料分类边界，让后续验收方拥有业务真值。真正的盲测访问隔离需在
R3.0-006 运行时只挂载 `modeling-input/`，并验证路径逃逸被拒绝；本轮没有 Agent runtime，不能把
仓库目录布局误报为强制访问控制。该设计也把“语义知识权限”和“业务数据权限”从文档、实现边界
到验收结论中明确拆开。

## 2. 当前平台盘点与差距

| 能力 | 当前证据 | v3.0 最终目标 | 本轮处理 |
| --- | --- | --- | --- |
| 项目/本体级主体 | Context Query 要求服务端 `AuthPrincipal` | 所有语义读取面主体绑定 | 记录基线，不改代码 |
| 细粒度语义可见性 | `SemanticVisibilityPolicy` 明示为 light labels、not full RBAC，且使用调用方 context label | 由 Project 级保护集约束受保护概念/映射的读取 | 记录 R3.0-004 缺口 |
| 项目级语义范围 | `SemanticQueryScopeResolver` 可汇聚项目内可查询 Ontology | 拓扑无关的场景全局视图 | 后续复用，当前不建模 |
| 关系 Schema 语义映射 | 未形成 v3.0 所需表/列/join/metric 合同 | Ontology 保存业务语义与映射 | 后续 R3.0-003 |
| 数据执行 | 平台没有本场景 Connector | 外部最小 SQL executor | 后续 R3.0-005 |
| 业务数据安全 | 不属于语义平台现有职责 | 外部系统/DB 执行 | 明确非目标 |

本轮不以文档、SQL 文件或数据库装载替代上述缺失能力的实现证据。

## 3. 目录与信息隔离

建模场景根目录：`docs/evaluation-scenarios/industrial-service-v3/`；业务真值位于独立的 delivery
reference 目录。

```text
industrial-service-v3/
├── README.md
├── verification/                       # tester-only 合同，不挂载给建模运行时
│   ├── schema-contract.json
│   ├── verify.sql
│   └── expected-results.json
└── modeling-input/                     # 后续建模运行时唯一挂载目录
    ├── input-manifest.json
    ├── scenario-brief.md
    ├── business-terms.md
    ├── schema.sql
    └── sample-data.sql

docs/delivery/reference/
└── industrial-service-v3-business-process-reference.md  # 业务真值

scripts/
└── load-industrial-service-v3-postgres.sh                # 安全装载入口
```

约束：

- `input-manifest.json` 是后续建模团队允许读取的文件白名单；不得引用
  `industrial-service-v3-business-process-reference.md`、`verification/`、本测试计划或预期 SQL 答案。
- `README.md` 只说明用途、装载方式、信息边界和安全声明，不补充业务真值。
- Schema 和样例 SQL 只维护一份，文档展示和数据库装载使用同一文件，避免漂移。
- SQL 不含密码、连接串或运行环境特有凭据。
- 当前静态测试证明分类和引用边界；R3.0-006 必须额外证明 Agent runtime 只挂载
  `modeling-input/`，且 `../`、仓库绝对路径和间接工具访问都不能读取业务真值。

## 4. PostgreSQL 数据模型

### 4.1 部署方式

- 使用现有 Compose PostgreSQL 服务和数据库。
- 所有场景对象放入专用 `industrial_service_v3` schema。
- 只通过 `scripts/load-industrial-service-v3-postgres.sh` 执行装载。脚本先验证 Compose 服务、当前
  数据库、SQL 中唯一允许的 schema literal，以及目标 schema owner/comment marker；任何不匹配都
  fail closed，不进入 DDL。
- `schema.sql` 可重入：只删除并重建这个明确命名的场景 schema，不触碰 `public`、平台表或其他
  schema。若目标 schema 已存在，必须同时满足 owner 为当前数据库用户且 schema comment 等于固定
  marker `ontology-platform:v3-industrial-service-fixture` 才允许重建；同名非 fixture schema 拒绝。
- loader 在装载前后计算非目标 schema relation sentinel（schema、relation、kind、owner 的稳定摘要）
  并要求相同；Schema DDL 和 seed DML 分别使用 `ON_ERROR_STOP` 与 transaction，失败不留下半批 seed。
- `sample-data.sql` 使用显式 ID、显式带时区时间和稳定顺序；重复装载通过重建场景 schema 获得
  确定结果，不依赖随机生成器。
- `schema.sql` 和 `sample-data.sql` 各自显式设置受控 `search_path`；业务表引用也必须限定在目标
  schema 解析。两个文件即使处于不同 `psql` 会话也不能落到 `public`。
- 不使用 Alembic：这些表是评估数据，不是平台产品存储。

### 4.2 表与职责

| 序号 | 表 | 主要职责 |
| --- | --- | --- |
| 1 | `service_regions` | 服务区域 |
| 2 | `customers` | 客户组织 |
| 3 | `service_sites` | 客户设备现场 |
| 4 | `equipment_models` | 设备型号 |
| 5 | `assets` | 已安装设备资产 |
| 6 | `sla_policies` | SLA 策略头 |
| 7 | `sla_targets` | 按严重程度的响应/解决目标 |
| 8 | `service_contracts` | 服务合同与有效期 |
| 9 | `contract_assets` | 合同覆盖资产与覆盖区间 |
| 10 | `incidents` | 客户报告的故障事件 |
| 11 | `work_orders` | 对故障执行的服务工单与关键里程碑 |
| 12 | `work_order_status_events` | 工单状态历史 |
| 13 | `technicians` | 服务工程师及区域/技能 |
| 14 | `work_order_assignments` | 工单分派历史 |
| 15 | `work_order_delay_events` | 延迟区间及确认原因 |
| 16 | `spare_parts` | 备件主数据；含受保护语义示例所用标准成本 |
| 17 | `part_compatibilities` | 备件与设备型号兼容关系 |
| 18 | `warehouses` | 区域仓库 |
| 19 | `inventory_movements` | 入库、预留、发货、调整等库存变动事实 |
| 20 | `part_requests` | 工单备件申请 |
| 21 | `part_shipments` | 申请的分批发运 |

### 4.3 关键约束

- ID 使用可读、确定性的 `text` 主键，便于建模样例与数据库结果对照。
- 关系由外键明确表达；多对多关系使用 `contract_assets`、`part_compatibilities`、
  `work_order_assignments`。
- 枚举字段使用 `CHECK` 约束，至少约束严重程度、工单状态、延迟原因、库存变动类型、申请/发运状态。
- 数量必须为正，成本不得为负，时间区间满足结束不早于开始。
- `incidents` 记录发生/报告时间；`work_orders` 记录响应、到场、恢复、解决里程碑。SLA 结果由查询
  派生，不保存一个可与里程碑冲突的冗余布尔结论。
- `work_order_delay_events.cause_code` 区分 `PART_SHORTAGE`、`DISPATCH_CAPACITY`、
  `CUSTOMER_ACCESS`、`OTHER`、`UNKNOWN`；只有事件记录本身才能支持延迟归因，不能仅因存在备件申请
  就推断“备件导致超时”。
- 成本列存在于 PostgreSQL 样例，但后续 Ontology 的成本概念/映射才是保护集可引用的语义资源；本轮对
  PostgreSQL 列没有用户级保护。

### 4.4 可机器复核的 Schema 合同

`verification/schema-contract.json` 冻结 21 张表的逐列合同：列名、顺序、PostgreSQL 类型、nullable、
default、主键、unique、外键目标及更新/删除行为、CHECK 表达式和必要索引。它同时保存
`schema.sql` 的 SHA-256，避免测试合同和建模输入中的 Schema 漂移。

独立验证从 `information_schema` 与 `pg_catalog` 生成实际结构，与合同做 exact comparison；表数、
PK/FK 数量或抽查约束只能作为诊断，不能替代逐项比较。合同至少显式覆盖
`spare_parts.standard_cost`、`incidents.failure_code`、所有工单里程碑以及合同/覆盖有效区间。

## 5. 代表性数据设计

数据量保持人工可核对，同时覆盖跨表复杂度：3 个区域、3 个客户、5 个现场、4 个型号、10 个资产、
2 个 SLA 策略、4 个合同，以及 10～14 个故障/工单。工程师、备件、仓库、库存、请求和发运数量按
覆盖案例需要设置。

必须包含以下命名场景：

| Case | 目的 | 数据特征 |
| --- | --- | --- |
| C01 | 备件短缺导致 P1 解决超时 | 合同有效；P1；PART_SHORTAGE delay；晚于目标解决；申请和发运可追踪 |
| C02 | 调度产能导致 P1 解决超时 | 合同有效；P1；DISPATCH_CAPACITY delay；无备件因果 |
| C03 | 有备件等待但 SLA 达标 | 有 part request/shipment；延迟未越过目标或非短缺原因 |
| C04 | 延迟原因未知 | delay cause 为 UNKNOWN；不得强行归因 |
| C05 | 合同失效或无覆盖 | 故障发生时没有有效 contract_asset；SLA 应为 not applicable |
| C06 | 重复故障 | 同一资产在固定窗口出现同类故障至少两次 |
| C07 | 部分发运且工单未完结 | requested > shipped；request PARTIAL；work order 非 RESOLVED |
| C08 | 正常对照 | 不需要备件、按时响应和解决 |

样例行只是发现结构和异常的证据，不在建模输入中解释上述 Case 的正确业务结论。

## 6. 业务流程参考设计

`docs/delivery/reference/industrial-service-v3-business-process-reference.md` 记录以下真值，但不进入
modeling input：

1. 在故障 `occurred_at` 时查找覆盖资产且有效的服务合同；不存在时 SLA 为不适用，而不是自动违约。
2. 按合同 SLA policy 和 incident severity 选择目标。
3. 响应时间从 `reported_at` 到 `responded_at`；解决时间从 `reported_at` 到 `resolved_at`。未解决时
   只能计算“截至查询时已耗时/是否已逾期”，不能伪造解决时长。
4. 备件短缺归因必须有 `work_order_delay_events.cause_code='PART_SHORTAGE'` 且延迟区间与工单相关；
   备件申请、库存为零或发运较晚本身只是相关证据。
5. 重复故障按同一资产、同一 failure code、滚动 30 天定义；是否属于同一次未解决事件需通过事件
   标识排除。
6. 一次修复要求首次现场到达后解决、没有第二次现场分派/重新打开；仅“最终已解决”不等于一次修复。
7. 指标必须声明粒度、时间字段、过滤条件、空值和分母规则。

文档还会列出后续访谈问题、保护受众示例以及能由数据库真值回答的 competency questions，供独立验收。

`verification/verify.sql` 把这些 Case 编码为稳定、只读的验证输出；
`verification/expected-results.json` 冻结 C01～C08 的业务 ID、关键时间/数量计算、每表行数、每表按
主键 canonical JSONB 排序后的内容摘要，以及明确的 NULL/empty fixtures。第二次装载必须逐表内容
摘要相同，不能只比较行数。

## 7. 安全与权限边界

本轮只设计、记录和准备权限验收素材，不实现权限：

- `ServiceOperator`：后续可见日常服务运营语义。
- `ServiceManager`：后续额外可见 `standard_cost`、备件成本和成本指标的语义与 Schema 映射。
- 当 Operator 查询无权成本语义时，未来语义接口必须遵循本次已确认、待 R3.0-004 文档统一修订的
  不存在/无痕过滤/SPARQL scope 合同，不能通过结果或 warning 泄露受保护知识。
- 当前 SQL 文件和开发数据库是评估环境资产，对能直接连库的开发者可见；这不构成权限测试失败，
  也不能作为生产数据权限设计。

## 8. 备选方案与取舍

1. **把样例业务行写入 RDF**：拒绝。违背用户确认的语义层边界，也会绕过实际 SQL 问数目标。
2. **只写 5～8 张宽表**：拒绝。无法充分暴露跨域 join、时序、履约和多对多建模问题。
3. **立即确定一个或多个 Ontology**：拒绝。当前缺少真实建模证据；切片边界先保持拓扑中立。
4. **本轮实现 SQL Adapter 或语义 RBAC**：拒绝。用户已选择准备/data baseline，提前实现会扩大
   当前完成门并混淆需求阶段。
5. **为评估表增加 Alembic migration**：拒绝。会把场景数据误提升为平台产品模型。

## 9. 实施顺序与停止条件

1. 冻结需求、设计和共享测试计划并通过强制计划审查。
2. 更新全局原则与术语，创建场景资料和同源 SQL。
3. 静态验证文件边界、SQL 结构和敏感信息。
4. 在专用 schema 装载并执行确定性数据库验证；允许一次基于测试发现的修复循环。
5. 由独立测试者按同一测试计划复核并记录轮次。
6. 同步需求/设计/交付记录状态并提交。

满足 R3.0-001 即停止。不得顺势创建 RDF、Ontology、Modeling Batch、Agent start、适配器或权限实现。

## 10. 风险与演进路径

- 数据库当前有一个既存 collation version mismatch 警告。本轮不修改全库设置；只要 schema/查询可
  正确执行，就记录为环境残余风险。
- 样例数据可能让建模 Agent从数据分布猜中部分规则，但不能因此删除 Schema/样例；后续验收重点是
  它是否把推测标为假设并主动访谈。
- 多 Ontology 下的项目级检索仍待 R3.0-002 细化；保护集已确认归属于 Project，可跨同一 Project
  的多个 Ontology，不能反向决定 Ontology 拓扑。该后续结论不改变 R3.0-001 的准备与数据验收。
- 最小 SQL executor 只适合受控评估环境。进入真实业务前必须由外部安全边界替换或包裹。
