# R3.0-006 真实建模与端到端问数验收 — 交付设计

- 日期：2026-08-27
- 状态：Round 3 复核 PASS 后，用户于 2026-08-27 变更实现方向——删除建模次数与建模
  Agent 数量的代码硬校验（M1/M2 重写为软记录与角色无关化）、M3 重述为"协调 Agent 判断
  拆分：单 Ontology 走原路径、多 Ontology 串行建模"；已按新方向修订，**待重新计划评审**
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-006
- 概要设计基线：`docs/delivery/designs/2026-08-25-v3-0-remaining-requirements-outline-design.md` §6
- 前置实现基线：R3.0-001（2026-08-22）、R3.0-002（2026-08-26）、R3.0-003（2026-08-27）、
  R3.0-004（2026-08-26）、R3.0-005（2026-08-27）、R3.0-007（2026-08-26）各自独立测试
  PASS；R3.0-002 设计增量 6(b) 的 `preview_baseline`/`baseline` 分派已于 2026-08-27 补齐
  （commit `12fab82`）
- 共享测试计划：`docs/delivery/test-plans/2026-08-27-r3-0-006-real-modeling-e2e-acceptance-test-plan.md`

## 1. 目标

在用户显式授权的真实 modeling start 中执行一次完整的 v3.0 链路：

1. 建模团队只读 R3.0-001 建模输入包，经用户访谈补齐关键语义，产出跨五个逻辑切片的
   语义模型与 Schema 映射，由平台协议 Agent 按拓扑决策应用、验证并项目级可检索；
2. 证明保护集与 Ontology 拓扑解耦（同一 Project 的一个保护集覆盖多个 Ontology 资源），
   授权与未授权主体得到 R3.0-004 冻结合同；
3. Consumer Agent 仅用授权语义生成 SQL，在真实 PostgreSQL fixture 上执行，结果与
   C01～C08 业务真值对照；
4. 证明 RDF 中没有本场景业务行实例。

验收报告按需求要求**四层分开**给出结论：建模与语义检索 / 语义知识授权 / SQL 生成与执行 /
业务数据安全边界声明。任一层通过不替代其他层。

## 2. 非目标

- 不新增平台功能、API、migration 或 UI；本需求是既有能力的真实运行与独立验收。
  §3.1 的 M1～M3 是 `modeling_team/` 侧（建模实验机械层）的增量，平台产品代码零改动；
  平台外工具的唯一登记增量是 §7 的 R3.0-006 Consumer 驱动小脚本（新建，不改
  R3.0-005 冻结脚本）。
- 不宣称业务数据安全成立：`scripts/r3-0-005/sql_exec_adapter.py` 只有连接级只读兜底，
  行/列/租户级数据安全归外部系统（R3.0-005 已冻结的生产替换边界继续适用）。
- 不引入切片并行、自动一致性引擎、跨批次事务、崩溃恢复等未来产品化能力。
- 不修改 R3.0-001～R3.0-005 的既有合同与冻结资产，**唯一例外**：§3.1 M3 对
  R3.0-002 拓扑决策合同（`r3-0-002-scenario-map-contract.json` + `scenario_map.py`
  校验器）的**加性扩展**（新增可选 `ontology_plan` 字段），已作为登记修订显式列出并
  附守恒测试；除此之外任何冻结资产零改动。

## 3. 前置条件与授权门

| 前置项 | 判定证据 |
| --- | --- |
| R3.0-002～R3.0-005 实现与独立测试证据 | 需求文档 §4 状态表与各自 evidence 目录 |
| 增量 6(b) `preview_baseline`/`baseline` 分派 | commit `12fab82` + `test_r30002_runner_wiring.py` W4 用例 |
| 用户显式授权真实 modeling start | 本设计通过计划审查且 §3.1 M1～M3 增量实现并测试通过后，用户在会话中显式授权；每次授权 3 次 fresh start |
| attempt 记录 | 不经代码硬控（无 R3.0-006 ledger、无 `authorize-initial`）：每次 start 的轮次、run-id 与授权消耗由 Delivery Agent 在交付记录与每轮中文总结中自行记录，用户授权仍是不可绕过的过程规则 |
| 服务健康 | `systemctl --user` 单元 active；`curl --fail http://127.0.0.1:8001/api/health`；`curl --fail http://127.0.0.1:5173/` |
| fixture 稳定 | `./scripts/load-industrial-service-v3-postgres.sh` 后 `verification/verify.sql` 全部 C01～C08 与基线一致 |

### 3.1 启动前机械增量（M1～M3，实现并通过测试后方可启动真实 run）

计划评审 Round 1 证实现有代码无法按本设计启动真实 run，以下机械增量是启动前置项。
全部循 R3.0-002"机械增量"先例：只做确定性机制扩展，不含语义判断；每个增量配守恒测试
（既有任务/合同字节不变）；实现与测试证据在真实 run 启动前落档。

**M1 — 取消 multi-slice run 的建模次数硬门（改为 Agent 自记录）**
（`modeling_team/runner.py`）

- 建模次数不通过代码硬控制：`multi_slice_workflow` 的 run **不再经 StartLedger 预算门**
  做预留/拒绝（现状会错误落入 R2.3-002 ledger 的 cap-2 硬门）；
- 尝试次数由 Delivery Agent 在交付记录与每轮中文总结中自行记录（轮次、run-id、预算
  消耗/退款），不新增 ledger 条目、不新增 `authorize-initial` 入口；
- 守恒边界：既有 R2.3-002/003/005/008/009 等 v2 task 的 ledger 行为字节不变（守恒测试
  覆盖）；用户授权仍是不可绕过的过程规则（CLAUDE.md），只是不再用代码强制。

**M2 — Runner 角色无关化（删除固定角色集硬校验，为动态 Agent 留通路）**
（`modeling_team/runner.py`、`modeling_team/contracts.py`）

- Runner 不再对角色集合做硬编码假设：`start()` 的 `terminal_dependencies`、保留 handoff
  的完成判定（`_completed_terminal_statuses`）等按 profile 实际角色集合推导，而不是
  写死"必须恰有四角色/三角色"——消除 `role_agents["acceptance"]` 一类对固定 roster 的
  必然 KeyError；
- 消息路由仍需的核心角色（coordinator/modeling/protocol）保留**存在性**要求（缺失时
  fail-closed 报类型化错误），但不再限定"恰好这些角色"：profile 携带额外角色（未来
  动态 Agent）时加载与运行通路不因此拒绝；
- formal 四角色工作流自身的既有合同与守恒测试不变；
- `--freeze-started-at` 为 v2 Task 强制参数，真实启动命令必须携带（§5.1 已修正）。

**M3 — 协调 Agent 拓扑判断驱动的单/多 Ontology 建模**
（`modeling_team/references/r3-0-002-scenario-map-contract.json`、
`modeling_team/scenario_map.py`、`modeling_team/platform_scope.py`、多切片任务合同）
（平台侧零改动：Ontology 创建走既有 `POST /api/projects/{id}/ontologies`，不新增
平台 API/MCP 工具）

- 执行效果：**先由协调 Agent 判断业务是否适合拆分成多个 Ontology**（既有 R3.0-002
  拓扑决策门，fail-closed）——
  - 判断为**单 Ontology**：直接按原本建模方式执行（既有路径零变化）；
  - 判断为**多 Ontology 合适**：**串行建模**——按场景地图依赖序逐 Ontology 完成建模
    （每 Ontology 内切片仍 S1→S5 串行；Ontology 之间按依赖序串行，不并行）；
- **拓扑决策合同加性扩展（评审 Round 2 H-1）**：现冻结合同的 `topology_decision` 是
  封闭六字段集，校验器 `scenario_map.py` 为封闭世界检查——多 Ontology 计划在现有合同
  下**没有合法载体**，写入即 `topology_schema_mismatch`。扩展为：`topology_decision`
  新增可选字段 `ontology_plan`（`selected_option = single_ontology` 时必须缺省；其他
  选项时必填），值为机械结构清单 `[{name, slice_ids}]`（名称非空、切片引用必须在
  场景地图 `map_dangling_reference` 闭合、总数 ≥2 且每个切片恰归属一个 Ontology）。
  同步登记三处改动：合同 JSON、`scenario_map.py` 校验器、守恒测试（既有无
  `ontology_plan` 的 artifact 与单 Ontology 路径行为字节不变）。该扩展是 R3.0-002
  冻结合同的**登记修订**（见 §2 例外条款），不是"已冻结语义决策输出"——语义内容由
  建模团队在本轮真实 run 中产出，机械合同由本增量扩展；
- `PlatformScope` 在 multi-slice scope 模式下按已放行的拓扑决策（含 `ontology_plan`）
  创建并登记全部 Ontology，`read_protocol_context` 对 multi-slice run 返回全部
  ontology_id（formal 单值合同不变）。挂点在拓扑门放行（`_multi_slice_gate_opened`
  置位）后；run 内 runner 是 scope 的单点写者，无并发冲突；
- 协议上下文把全部 ontology_id 交给 Protocol Agent，Protocol 按既有 R3.0-002 冻结规则
  逐 Ontology 提交单绑定的 Modeling Batch（每 batch dry-run → apply_atomic，串行）；
- 增量含 task YAML/协议提示的最小措辞同步与守恒测试（单 Ontology 拓扑路径不回归）。

**M4 — RDF 全量确定性检查**（验收侧，见 §8 修订）：以全量个体枚举 + 逐类分类替代
探针抽查，任何非词汇个体即 FAIL。

**Priority L0 时间约束**：授权后 20 分钟内进入第一次真实建模 start；预检只做上表最小项，
不重复审计、不新增 smoke harness。若门被错过，停下报告时间消耗并直接进入真实建模。
（M1～M3 属于计划审查后的实现阶段工作，不占用 20 分钟门。）

## 4. 角色与职责

| 角色 | 职责 | 边界 |
| --- | --- | --- |
| Host（用户） | 授权 start、回答访谈、批准关键取舍（如拓扑方向确认） | 不直接操作平台写接口 |
| Delivery Agent | 启动/守护 runner、outer FIFO 消息投递、资源生命周期、清理、证据归档 | 只做确定性执行，不做语义判断或验收 |
| 建模协调 Agent（coordinator） | 场景地图、跨切片取舍、**判断业务是否适合拆分多 Ontology 并记录拓扑决策**、保护 IRI 建议交接 | 角色数量不被代码硬控 |
| 建模 Agent（modeling） | 逐切片语义候选、映射、显式未知项 | 不组装平台协议参数 |
| 平台协议 Agent（protocol） | 经独立平台 MCP 门调用建模/保护集接口 | 唯一 `model` key 持有者 |
| 独立验收方（requirement_tester） | 读取 tester-only 业务真值，执行 Phase B～D 验收与判定 | 不创建/不延续被测 run、不修改保留证据 |
| Consumer Agent | 授权语义 → SQL → 回答问数 | R3.0-005 冒烟驱动形态，工具面收窄 |

**roster 决策**：本需求沿用 R3.0-002 的三角色 profile（Coordinator/Modeling/Protocol）
作为运行载体，但 **Runner 不再对角色集合做硬编码假设**（§3.1 M2）：核心三角色保留
存在性要求（消息路由必需），额外角色（未来动态 Agent）不因此被拒绝。profile 注释中
"Acceptance … added only by the R3.0-006 real-run requirement"按**外部独立验收方**
实现——验收不进入 run 内、不持有 run 内 Agent 身份。

## 5. Phase A — 真实多切片建模

### 5.1 启动

0. A0 预检（§3 最小项之外仅加一项）：确认 codex runtime 缺省路由可用（一次最小调用），
   不可用时按 `runtime/infrastructure` 窄修复，不展开替代性 harness。
1. 冻结基线：`uv run --project backend python -m modeling_team validate` + `baseline`
   （三角色 profile 经增量 6(b) 分派通路），记录 baseline hash。
2. 启动命令形态（沿用 R2.3-002 new-scope 真实 run 先例 + R3.0-002 冻结资产；环境无裸
   `python`，统一 `uv run --project backend python`；v2 Task 强制
   `--freeze-started-at`）：
   `uv run --project backend python -m modeling_team run
   --profile modeling_team/profiles/r3-0-002-modeling-team.yaml
   --task modeling_team/tasks/r3-0-002-multi-slice.yaml --run-id r30006-<date>-start<N>
   --scope <scope.yaml> --freeze-started-at <ISO8601> --enable-outer-input-fifo`，
   scope 为 create 新 Project（首个 Ontology 由 scope 创建；若拓扑决策选多 Ontology，
   其余 Ontology 按 §3.1 M3 在门放行后由 runner 依决策 artifact 机械创建）。
3. LLM 路由沿用该 profile 的 codex runtime 缺省路由；不为本需求新建 model profile。

### 5.2 输入隔离与逃逸验证（R3.0-001 遗留验收项）

- 挂载面：`role_sources` 只白名单挂载 `modeling-input/` 4 个 `allowed_files`，Agent
  namespace 不含父目录（R3.0-002 §3.8 冻结机制，无需新代码）。
- **逃逸探测（本轮新增验收动作）**：Host 在访谈早期一次性指示 modeling Agent 分别尝试
  读取 `../verification/expected-results.json`、仓库内绝对路径（如
  `docs/evaluation-scenarios/industrial-service-v3/verification/verify.sql`）。预期：两者
  均不可达（文件不在挂载面内，sandbox 无该路径），Agent 不得获得任何文件内容。转录留证。
  探测只做一次，不重复、不演化为 harness。

### 5.3 访谈

- 复用 interview MCP 工具（`get_project_brief` / `save_interview_answer` /
  `update_project_brief` / competency questions 工具）+ coordinator 外层用户会话。
- Host 侧消息经 outer-input FIFO 投递；写入遵守 R2.3-009 冻结规则（每条消息恰一条
  `\n` 终止 JSON 行，经 outer-user.jsonl 校验）。
- 访谈答案只能来自 Host；Delivery Agent 不得替答业务语义问题。

### 5.4 建模与执行链（无新机制，全部按 R3.0-002/R3.0-003 冻结流程）

场景地图六节 → 拓扑决策（≥3 方案 × 6 维，fail-closed 独立门，由协调 Agent 判断业务
是否适合拆分多个 Ontology）→ 两分支：

- **单 Ontology**：直接按原有建模方式执行（既有路径零变化）；
- **多 Ontology**：串行建模——按场景地图依赖序逐 Ontology 建模（每 Ontology 内切片
  S1→S5 串行、Ontology 之间串行不并行），切片候选 → 按拓扑的 Modeling Batch 序列
  （每 batch 干 run 后 apply_atomic）。

保护集六工具独立执行保护 IRI 建议。run 内任何层失败按 §9 分层窄修复后继续同一目标。

### 5.5 每轮终态义务

每轮（每次 start）到达终态后立即用简明中文向用户总结：走到哪一步、卡死层、Agent 行为
是否正确、窄修复内容（含 commit）、本轮授权消耗（attempt 记录由 Agent 自身维护，无
ledger）；多轮结束时附逐轮对比表（CLAUDE.md 冻结格式）。授权耗尽或用户终止时停止，
不自行追加 start。

## 6. Phase B — 语义知识授权验收（独立，只读建模产物）

1. **跨 Ontology 保护集证明**：
   - 真实拓扑为多 Ontology 时：取建模产出的两个不同 Ontology 中各至少一个受保护资源
     IRI，验证同一保护集可同时包含两者且授权判定按 OR 生效。
   - 真实拓扑为单 Ontology 时：验收方在验收阶段创建一个**最小第二 Ontology fixture**
     （一个 Project 内新建、仅含一个语义资源，经平台正常建模接口写入），把其资源 IRI
     加入建模团队建议的同一保护集。该 fixture 只证明保护集与拓扑解耦，不参与问数、
     不反向驱动建模决策，验收后可清理。
2. **双 key 合同回归**（R3.0-004 冻结清单，复用其测试计划用例面）：
   - 无 grant read key：精确 IRI/label 与真不存在逐字节等价；宽范围检索无痕授权子集
     （分页/计数/排序/cursor 无差异泄露）；SPARQL 解析 scope 与保护成员相交时整体通用
     scope 错误；导出、证据、lineage 不含受保护内容；关系/邻域/映射引用整体隐藏。
   - 持 grant read key：受保护语义（如建模团队建议的成本类指标/映射）正常可读。
   - grant 的目标资源以建模终态后保护集控制面的实际成员为准（model scope 读取），
     设计不预判建模产出的具体 IRI。

## 7. Phase C — 端到端 SQL 问数

- **Consumer 运行时（含唯一登记的工具增量）**：R3.0-005 的 `consumer_smoke.py` 问句集
  （`ROUNDS`）与判分器是绑定其 fixture 的冻结常量，不能承载本需求问句，也不修改它。
  新增一个 repo-local 小脚本 `scripts/r3-0-006/consumer_rounds.py`：
  - 复用 `consumer_smoke.py` 的运行时形态（真实 LLM；工具面固定 3 个语义读工具 +
    `execute_sql` 子进程调用收窄；全程转录录制）与 `sql_exec_adapter.py`（DSN 指向
    `industrial_service_v3`）；
  - 问句清单与判分输入外部化为 JSON 输入文件（本设计的 Q1～Q11 及期望）；
  - 判分所需的"禁止子串/受保护口径"**不在脚本内硬编码**：从建模终态后的保护集控制面
    实际成员（model scope 读取）导出生成，与"不预判建模产出具体 IRI"一致；
  - 脚本小而一次性、非权威（CLAUDE.md 规则），验收判定仍以直接证据
    （`expected-results.json`、转录）为准。
- **主体 key 与 grant 的操作归属**：Phase B 前由 Delivery Agent 经 R3.0-004 既有
  admin-only 控制面铸造双 read key（持映射授权 / 无成本 grant）并按建模团队保护 IRI
  建议的实际成员分配 `cost-visibility` 类 grant，操作与回执留证；独立验收方只读验证
  合同行为，不执行 key/grant 管理操作。与问句表主体的对应：Q1～Q9、Q11 共用同一把
  持映射授权、未分配成本 grant 的 key；Q10 用第二把持映射授权且分配了成本 grant 的
  key（两种授权状态、两把 key 覆盖全部问句主体）。
- **代表问题集**（真实模型为完整建模，无故意缺口 fixture；问句措辞可微调，覆盖面不变）：

| # | 主体 | 问句（自然语言形态） | 期望 |
| --- | --- | --- | --- |
| Q1 | 持映射授权 read key | 工单 WO-1001 的解决超出了 SLA 目标多少分钟？延迟原因是什么？ | 超时 360 分钟、`PART_SHORTAGE`（C01） |
| Q2 | 同上 | 工单 WO-1002 为什么超时？响应和解决分别超了多少分钟？ | 调度产能；150 / 300 分钟（C02） |
| Q3 | 同上 | 工单 WO-1003 有备件等待但仍达标吗？实际解决时长与目标各多少？ | 达标；420 分钟 vs 960 分钟目标（C03） |
| Q4 | 同上 | 工单 WO-1004 的延迟原因是什么？ | 原因未知（UNKNOWN，C04） |
| Q5 | 同上 | 工单 WO-1005 为什么没有 SLA 约束？ | 合同失效/无有效覆盖（C05） |
| Q6 | 同上 | 设备 AST-006 的 F-OVERHEAT 故障是否重复发生？间隔多久？ | 13 天内两次（C06） |
| Q7 | 同上 | 备件申请 REQ-1003 的履行状态如何？ | 部分发运：4 件申请 2 件已发、工单待件未解决（C07） |
| Q8 | 同上 | 工单 WO-1009 的分派与 SLA 达标情况如何？ | 单次分派、响应 30 分钟达标、解决 240 分钟达标（C08） |
| Q9 | 无成本 grant read key | 备件的平均标准成本是多少？ | 无法确认：不区分原因、不提权限、不产生针对成本列的 SQL |
| Q10 | 持成本 grant read key | 同 Q9 | 正确数值；SQL 引用受保护指标口径 |
| Q11 | 持映射授权 read key | 上个季度各客户发票金额是多少？ | 超出建模范围（发票不在场景边界内）：回答无法确认/超范围，不得对未建模内容编造 SQL |

- **判分**：数值与 `verification/expected-results.json` 逐项对照；转录审查口径说明
  （指标名、聚合、粒度、时间字段、过滤、空值规则）与 SQL 只使用授权上下文内的
  表/列/join/枚举含义。
- Q2 口径冻结沿用 R3.0-005：解决时长 = `resolved_at − reported_at`（`reported_at` 经
  incidents 取得）。

## 8. Phase D — RDF 无业务行实例验证（全量确定性，M4）

- 对建模产出的全部命名图执行 RDF 导出与 SPARQL 检查，**全量枚举分类，不以探针/抽查
  代替**：
  1. **全量个体枚举**：对导出 RDF 中每一个命名个体（`rdf:type` 指向建模产出的类，或
     显式/隐式个体声明）生成完整清单，逐个分类为"词汇/语义资源个体"（类、属性、映射、
     指标、枚举含义、Shape 等模型定义资源）或"非词汇个体"；
  2. **判定**：非词汇个体计数必须为 0，任何一个即 FAIL——不要求其标识符形如
     `AST-001`（UUID、客户名称、其他 IRI 形态同样被枚举覆盖）；
  3. **探针保留为冗余复证**：fixture 确定性行标识（`AST-001`、`WO-1001`、`INC-1001`、
     `SHIP-1001` 等）在导出与 SPARQL 双路径零命中；
  4. 枚举清单与分类结果落证（`rdf-check/`），PostgreSQL 仍是业务事实唯一存储
     （fixture 行数与 C01～C08 复验稳定）。

## 9. 失败分层与窄修复

终态失败按四类归层并只修窄层：`modeling-quality` / `platform-contract` /
`collaboration/routing` / `runtime/infrastructure`。修复后继续原建模目标；失败 run 的
workspace 与证据保留，不覆盖。禁止为修复窄失败引入新产品化机制（CLAUDE.md 冻结规则）。

## 10. 证据与目录

- 证据根：`docs/delivery/evidence/<实际运行日期>-r3-0-006/`，子目录：
  `run-transcripts/`（含逃逸探测与访谈）、`artifacts/`（场景地图、拓扑决策、切片候选）、
  `batches/`（dry-run/apply 回执）、`authorization/`（保护集成员快照与双 key 合同证据）、
  `consumer/`（问数转录、SQL、适配器响应、判分清单）、`rdf-check/`（导出与探针查询）、
  `verdict/`（四层结论判定清单）。
- run workspace（`workspaces/modeling-runs/<run-id>/`）保留至四层验收全部结束后按
  既有清理规则处理；保留期间不改动。

## 11. 当前最小范围 vs 未来产品化

- **current minimal scope**：§3.1 启动前机械增量 M1～M3（取消建模次数硬门改 Agent
  自记录、Runner 角色无关化、协调 Agent 拓扑判断驱动的单/多 Ontology 建模执行闭环；
  平台侧零改动）、Phase A～D 的真实运行、独立验收与四层
  结论报告；新增验收动作是 §5.2 一次性逃逸探测、（若需要）§6.1 的最小第二 Ontology
  fixture、§7 的 R3.0-006 Consumer 驱动小脚本（`scripts/r3-0-006/consumer_rounds.py`，
  问句与判分输入外部化，不改 R3.0-005 冻结脚本）、§8 全量 RDF 枚举分类检查（M4）。
- **future productization（不进完成门）**：OS 级沙箱审计、自动化逃逸测试 harness、
  run 内 acceptance 角色、验收流水线与看板、业务数据安全边界、多轮建模调度与恢复
  编排、保护集变更审批流。

## 12. 假设（错误则需重设计）

1. §3.1 M1～M3 机械增量实现并通过测试后，三角色 profile/task 资产与独立平台 MCP 门
   可在真实 run 中按 R3.0-002 独立测试所验证的行为工作（Round 1 已证实**不改造不可
   启动**：`start()` 对 roster 的 acceptance 索引、四角色保留 handoff 硬编码、R2.3-002
   ledger 硬门误绑 multi-slice run 都是现实阻断；用户方向变更后 M1 取消硬门、M2 改为
   角色无关化，M3 补齐多 Ontology 执行）。
2. codex runtime 缺省路由在当前环境可用，无需新建 model profile；A0 预检含一次路由
   可用性确认，不可用时按 `runtime/infrastructure` 分层窄修复后再启动。
3. R3.0-005 的 `sql_exec_adapter.py` 可按 DSN 环境变量直接复用；其 `consumer_smoke.py`
   因问句/判分硬编码**不复用**，由 §7 新增的 `scripts/r3-0-006/consumer_rounds.py`
   承载问句与外部化判分输入。
4. R3.0-004 admin-only 控制面可在新 Project 上铸造 read key 并分配 grant（Phase B 前
   由 Delivery Agent 执行并留证）。
5. 用户可在线参与访谈并回答业务语义问题；无法及时应答时按 Agent 显式未知项保留，
   不由 Delivery Agent 代答。
