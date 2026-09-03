# R3.0-008B 建模决策分阶段流程与值语义联合验收 — 交付设计（第一段：机械增量）

- 日期：2026-09-03
- 路径：`docs/delivery/designs/2026-09-03-r3-0-008b-staged-modeling-decision-and-value-acceptance-design.md`
- 状态：计划评审通过（2026-09-03。Round 1 REVISE：两项 accepted-high——阶段 3 链式门
  latch/close 死锁（修订为先决检查模型）、新 artifact 目录沙箱无可写通路（修订为逐角色
  定向 bind）；Round 2 复核 REVISE：修订引入 High-3——可选单文件 artifact 的 bind 语义
  不闭合（修订为角色独占子目录 + 目录 bind + prepare 期只 mkdir）；Round 3 窄确认 PASS。
  同日用户外部评审四项发现全部核实为真并修订：①提交信封错位（§3.6 改为
  `submit_modeling_batch` 真实签名镜像 + `inspect.signature` 对照验收）；②capability 端点
  分派遗漏 `acceptance.py` 接线与写转发器组件（附录 A 补齐；明确不复用只读
  `McpReadForwarder`）；③批准归属不闭合（新增 coordinator 独占 approvals artifact 与
  交叉校验）；④未知提交结果不可恢复（新增 durable intent、固定幂等键与确定性恢复规则）。
  三项评审假设处置：TableMapping 不设门与裸 create_entity 提前建 L3 均登记 §4.2 边界，
  写路径转发 model key 维持假设 2 待第二段实测）。按用户已确认的细化合同执行**两段式交付**：第一段=阶段门 / artifact
  schema / Runner 校验 / 三角色 prompt 增量（本设计主体，`modeling_team/` 内，backend 零改动），
  独立测试 PASS 后冻结；第二段=真实建模运行联合验收（挂 R3.0-006 授权体系，且待 R3.0-009
  机械增量完成后执行）。两段证据不互相替代。
- 实现结果（2026-09-03）：第一段按附录 A 全量交付（backend/frontend 零 diff）。开发者自测
  轮 + 独立测试 Round 1（两项 Low 缺陷：六个 reason code 无显式用例、monitor tick 损坏
  intent/receipt JSON 异常未收敛）窄修复后 Round 2 复测全绿（modeling_team 1181 通过 /
  1 跳过、backend 957 通过零 diff、ruff 零新增、validate CLI 双通过、F4/F5 账面干净）。
  L2 真实 Runner 机械 smoke 因 codex 模型 API 外部 404 两次无法执行，经用户裁决跳过
  （见测试计划收口裁决节，不得解读为 L2 PASS）。第一段冻结；第二段待 009 机械增量 +
  006 授权。证据：`docs/delivery/evidence/2026-09-03-r3-0-008b/`。
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-008B 全节（分阶段流程与决策时点、角色职责、
  最小验收条件、非目标），及文件头部当前状态区对 008A/008B 证据不可互替的冻结声明
- 冻结依赖合同（本设计只在其上增量，不改任何已冻结合同）：
  - `docs/delivery/designs/2026-08-26-r3-0-002-multi-slice-modeling-workflow-design.md`
    （场景地图六节合同、拓扑决策门、独立平台 MCP 门、保护 IRI 建议交接——008B 阶段门直接
    复用该门机械与 artifact 模式）
  - `docs/delivery/designs/2026-09-03-r3-0-008a-controlled-value-semantic-chain-design.md`
    （L1/L2/L3 表达合同、`semanticValue`、G7 结构校验——008B 不重复建设任何映射资源合同）
  - `docs/delivery/designs/2026-08-27-r3-0-006-real-modeling-e2e-acceptance-design.md`
    （真实 modeling start 授权体系与 attempt 预算——第二段执行框架）
- 越界登记（本设计不实现）：R3.0-009 共性抽象详细合同（阶段 3 仅最小槽位门，待 009 细化后
  回填）、R3.0-010 接口信息映射源（unlock 记录仅登记 `source_type` 取值面）、真实建模运行与
  联合验收闭环（第二段）
- 共享测试计划：
  `docs/delivery/test-plans/2026-09-03-r3-0-008b-staged-modeling-decision-and-value-acceptance-test-plan.md`
- 交付边界：R3.0-002 Team Runner + 三 Agent 包基线上的机械增量；**backend/frontend 零
  diff**（论证见 §3.9）；第一段验收载体为 002 同款确定性机械校验 + fixture 任务条目，零
  apply、零 RDF 写、零建模 attempt；不验收语义质量与真实联合验收（归第二段）

## 1. 目标

1. **七阶段时点门机械落地**：把需求定义的"场景理解 → 逻辑切片 → 平台中立基础图候选与共性
   抽象 → Ontology 拓扑决策 → 基础业务语义建模（含值分析）→ 数据库映射与值语义物化 →
   联合验收"顺序变为 Runner 可确定性检查的时点门：产物存在性、结构、引用闭合与执行顺序
   （fail-closed、typed reason code、可自愈），不评判内容优劣。
2. **`analyzed_not_materialized` 分析结论 artifact**：受控值候选在数据库编码未确认时只有可
   追溯的分析结论（窄口径：仅受控值候选；一般性显式未知项留在 002 场景地图/切片 artifact）。
   字段级 schema、`analyzed → confirmed → materialized | conflict` 状态机、以新版本取代旧版本
   并保留历史的修订规则，全部机械可校验。
3. **物化时点门**：`create_enum_meaning` / `update_enum_meaning` / L3 值节点创建必须回溯到
   `confirmed` 状态分析结论，按 `mapped_property` + 候选值机械匹配；编码冲突置 `conflict`
   退回业务确认；无数据库 Schema 且无接口信息时允许登记式跳过（受控值保持分析结论）。
   阶段 5 期间物化命令 fail-closed 阻断。
4. **阶段 7 联合验收清单 artifact**：七个固定验收项（业务语义召回 / 共性召回 / 跨切片跨
   Ontology 召回 / 值语义召回 / SQL 映射链 / 008A 代表问题「查询因为缺料而延期的订单」真实
   复验 / RDF 无业务行）的结构合同；第一段只做结构校验，verdict 语义判定归第二段。
5. **零 backend 改动**：物化门在 modeling_team 侧对批次提交做前置机械检查（§3.6、§3.9）；
   backend 既有 dry-run/apply 完整性校验（008A 交付的 G7 等）一字不动，仍是结构最后一道防线。
6. **交付本身可被确定性验证**：新增模块为纯机械函数（`scenario_map.py` 同款），Runner 接线、
   capability 拒绝/通过路径、守恒（无参数任务零行为变化）全部可单测，smoke 任务条目零建模写。

## 2. 非目标

1. 不重复实现 R3.0-008A 已冻结的映射资源合同（`EnumValueMeaning`、`semanticValue`、G7、
   读取投影）；008B 只定义阶段时点、产物与批准关系。
2. 不实现 R3.0-009 的共性识别、关系提升、协调确认详细合同；阶段 3 只做最小槽位门（产物
   存在 + 批准记录），槽位 schema 待 009 细化后以登记修订回填（先例：R3.0-006 M3 对 002
   六字段记录的 `ontology_plan` additive extension）。
3. 不实现 R3.0-010 接口信息映射源；unlock 记录的 `mapping_sources` 仅登记 `source_type`
   取值面，不做任何接口源专门分支。
4. 不在第一段执行真实建模运行、不消费建模 attempt 预算、不验收联合验收闭环、不验收语义
   质量；不把 checklist 的 `pass` verdict 作为第一段可宣称的结果。
5. 不新增 backend 表/API/migration/MCP 工具、不新增 RDF 字段或谓词、不改 `SAFE_PROTOCOL_TOOLS`
   字节；分析结论与门状态存 repo-local 共享运行目录，不进 backend 表/RDF。
6. 不建设编排框架、长期版本治理、管理 UI、自动 Schema 演进（需求非目标逐条落实）；不做
   拓扑/切片/值表达的内容评分。

## 3. 功能合同

### 3.1 交付形态与复用基线（第一段 current minimal scope）

按 CLAUDE.md「复用最近已验收基线」规则，完整复用 R3.0-002 机械基线（`scenario_map.py`、
`candidate_platform_gate.py` 门载具、`contracts.py` 参数通路、`profiles/r3-0-002-modeling-team.yaml`
三角色 roster、`references/` 合同 JSON、`tasks/` 条目、monitor tick 反馈机制），以及 R2.3 已
验收的 host 侧代理先例（`capability_mcp.py` Runner-private capability broker、
`modeling_readonly.py` 的「宿主侧校验 + 注入式转发 + 回执摘要」模式）。增量如下：

| # | 增量 | 性质 |
| --- | --- | --- |
| 1 | `modeling_team/staged_decisions.py` | 新纯机械模块：008B 全部 artifact 合同 loader + 结构校验 + 状态机/匹配规则 + 确定性 reason codes + 平台批次对账纯函数（`scenario_map.py` 同款，无 I/O 副作用） |
| 2 | `modeling_team/contracts.py` 参数扩展 | v2 Task `parameters` 封闭键集新增 `staged_modeling_decisions`（boolean；为 true 时必须同时声明 `multi_slice_workflow: true`，否则 `TeamConfigurationError`），配套守恒校验 |
| 3 | `modeling_team/runner.py` 门接线 | monitor tick 中 `_check_staged_decision_gates()` 在 `_check_multi_slice_topology_gate()` **之前**执行：阶段 3 槽位先决检查（槽位不合格则本 tick 跳过拓扑检查，见 §3.4）、阶段 7 checklist 结构门（终态前必须存在且合格）、ledger/receipt 交叉校验、门 kill-switch；反馈复用 `_deliver_multi_slice_gate_feedback` 机制（kind=`staged-decision-gate`） |
| 4 | `modeling_team/capability_mcp.py` + `acceptance.py` 分派 + `runner.py` handler | 新 Runner-private 协议操作 `protocol_staged_submit_modeling_batch`：staged 任务中批次提交的唯一通路——前置机械检查（§3.6）通过后先写 durable intent，再经**新增 host 侧写转发器**（非 `McpReadForwarder` 只读 allowlist）以协议 Agent 的 model key 原样转发 `submit_modeling_batch`，并写权威 submission receipt；失败返回 typed reason code（fail-closed、可自愈重试）。操作注册进 `capability_mcp.py` 后还须经 `acceptance.py` 的 `RunnerCapabilityEndpoint` 分派接线并进广播面——capability 端点的 operations 集合按 role 在该文件组装，漏接则 staged 任务中该操作不存在合法调用路径 |
| 5 | `modeling_team/references/r3-0-008b-staged-decisions-contract.json` | 新 Agent 可读 artifact 合同（挂载给三角色，先例 `r3-0-002-scenario-map-contract.json`） |
| 6 | `modeling_team/tasks/r3-0-008b-staged-decisions-smoke.yaml` | 新机械 smoke 任务（零建模写，见测试计划） |
| 7 | `modeling_team/tasks/r3-0-008b-staged-real.yaml` | 新真实分阶段任务条目（冻结配置资产；条目内注明：R3.0-009 机械增量完成且用户经 R3.0-006 授权 modeling start 前不得启动） |
| 8 | agent-packages 指令最小增量 | coordinator/modeling/protocol 三处 `instructions.md` 各加一节「Staged modeling decisions (R3.0-008B)」，只写角色、时点义务与拒绝行为（§3.8），不写任何业务语义 |
| 9 | `modeling_team/runtimes/codex.py` 沙箱 bind + 广告增量 | staged 任务逐角色新 artifact 目录可写 bind（复用 `_coordinator_scenario_map_bind`/`_thread_sandbox` 先例；唯一写者约束见 §3.9）+ staged capability 操作广告分派；非 staged 任务的沙箱 bind 集与 002 基线逐字节一致（F1 守恒） |

**平台零改动声明**：本需求第一段不新增 backend 表/API/migration/前端，不改任何 backend
产品代码（论证见 §3.9）。机械事实已验证：`submit_modeling_batch` 的 `enabled_tools` 面由任务
`protocol_tools` 配置（`protocol_mcp_launch.py`），可配置层面收口；host 侧「校验 + 转发 +
回执」先例已验收（`modeling_readonly.py` `_forward` 注入、`acceptance_runtime.McpReadForwarder`）；
`update_enum_meaning` 载荷不含 `property_iri`（`modeling_handlers.py` 约 309 行），是 §3.6
匹配规则区分 create/update 的依据。

### 3.2 七阶段时点门总览（门矩阵）

staged 任务 = `multi_slice_workflow: true` + `staged_modeling_decisions: true`（依赖关系
机械强制）。各阶段的输入产物、门载体、机械条件与自愈路径：

| 阶段 | 时点门载体 | 机械条件（Runner，全部确定性） | 失败形态（reason codes） | 自愈 |
| --- | --- | --- | --- | --- |
| 1 场景理解与访谈 | 无独立门（002 输入边界 + 场景地图 `explicit_unknowns` 承载一般性未知项） | — | — | — |
| 2 逻辑切片分析 | 002 场景地图结构门（既有，零改动） | 六节键齐备、引用闭合、共享术语唯一 owner | `map_*`（002 §5，零改动） | 补齐 artifact 后重试 |
| 3 平台中立基础图候选与共性抽象（009 最小槽位） | 先决检查（staged 检查先于拓扑检查：槽位不合格则本 tick 不执行拓扑检查、门保持 closed、不置 002 latch） | `stage3-neutral-graph/neutral-candidate.json` 存在、可解析、schema 匹配、`approved_by` 非空、`candidate_artifacts` 非空且逐项存在非符号链接；approvals 中存在对应 `stage3_slot` 记录（§3.6b） | `stage3_missing_artifact` / `stage3_unparsable` / `stage3_schema_mismatch` / `stage3_missing_approval` / `stage3_approval_record_missing` / `stage3_candidate_artifact_unavailable` | 补齐槽位 artifact，下个 tick 自动重评 |
| 4 Ontology 拓扑决策 | 002 拓扑门（既有条件零改动；staged 任务先过阶段 3） | 002 §3.3 全部条件（三方案六维度、选择、理由、ontology_plan 闭合） | `topology_*`（002 §5，零改动） | 002 自愈路径 |
| 5 基础业务语义建模 + 受控值分析 | capability 前置门（§3.6）：含枚举物化命令的提交在无有效 materialize 模式 unlock 时拒绝；受控值候选只能产出分析结论 artifact | 分析结论 artifact 结构合法；批次不含枚举物化命令即可照常提交（与候选值无关的核心业务语义可继续建模） | `staged_value_materialization_locked` / `staged_conclusions_unavailable` / conclusions 系（§4.1） | 协调 Agent 确认编码后登记 unlock，或修订结论后重试 capability |
| 6 数据库映射与值语义物化 | capability 前置门：逐命令回溯 `confirmed` 结论，按 `mapped_property`+候选值机械匹配；conflict 拦截；skip 登记式放行 | §3.6 匹配规则全过 + unlock `mode=materialize` 有效（或 `mode=skip` 时枚举命令永久拒绝、结论保持 analyzed） | `staged_missing_trace` / `staged_conclusion_not_confirmed` / `staged_conclusion_conflict` / `staged_conclusion_already_materialized` / `staged_trace_mismatch` / `staged_unknown_enum_target` / `staged_l3_unapproved` / `staged_dangling_semantic_value` | 修正结论（新修订）/补 unlock/更正 trace 后重试 |
| 7 联合验收 | checklist 结构门（monitor）：终态前 `joint-acceptance/joint-acceptance-checklist.json` 必须存在且结构合格 | 七个固定 item_id 各恰一条、字段合法（§3.7）；verdict 判定归第二段 | `acceptance_checklist_missing` / `acceptance_checklist_unparsable` / `acceptance_checklist_schema_mismatch` | 修复 checklist 结构 |

顺序强制的机械汇总：阶段 3→4 由**先决检查顺序**承担（staged 检查先于拓扑检查执行；
槽位不合格时本 tick 直接以 `stage3_*` 反馈保持门 closed 并跳过拓扑检查——不置 002 的
`_multi_slice_gate_opened` latch，也不调用 `close()`；槽位合格后拓扑检查照常执行且只
开闸一次）；阶段 4→5/6 由 capability 拒绝
`staged_gate_closed`（门未开时任何提交拒绝）承担；阶段 5→6 由 unlock 登记承担。

### 3.3 `analyzed_not_materialized` 分析结论 artifact（`r3-0-008b-analysis-conclusions/v1`）

- **维护者**：建模 Agent 产出分析、建模协调 Agent 批准状态推进（批准的机械证据是
  coordinator 独占 approvals artifact 中的对应记录，§3.6b；`confirmed_by` 字符串仅为展示
  信息）；Runner/工具只做结构校验。
- **位置**：`workspaces/modeling-runs/<run-id>/value-semantics/conclusions/analysis-conclusions.json`（当前
  版本）+ `value-semantics/conclusions-archive/<conclusion_id>.r<rev>.json`（历史版本，
  不可变文件）。repo-local 共享运行目录，不进 backend 表/RDF。
- **窄口径**：entries 只覆盖受控值候选；一般性显式未知项留在 002 场景地图 `explicit_unknowns`
  与切片候选（机械上本 artifact 不设 general-unknown 字段，交界清晰）。

顶层字段（封闭集合）：`schema_version`、`scenario_id`（非空）、`maintained_by`（非空，建模
Agent 身份）、`entries[]`（可为空列表——场景无受控值候选时合法）。

entry 字段（封闭集合，逐字段机械要求）：

| 字段 | 类型 | 机械要求 |
| --- | --- | --- |
| `conclusion_id` | str | 非空、entries 内唯一；跨修订稳定（建议 `ac-####`，机械只要求非空唯一） |
| `mapped_property` | str | 非空绝对 IRI（复用 002 `_ABSOLUTE_IRI` 形状；候选值所属属性） |
| `candidate_value` | str | 非空（业务层候选值标识，如「缺料」；不是数据库编码） |
| `business_meaning_hypothesis` | str | 非空（业务含义假设） |
| `evidence_refs[]` | list[str] | 非空且每项非空（证据引用：访谈答案 id、输入文件锚点、样例观察 id 等，格式自由） |
| `proposed_level` | enum | `L1` / `L2` / `L3`（建议表达层级） |
| `blocking_unknowns[]` | list[str] | 可空；每项非空（阻塞未知，如「数据库实际编码未确认」） |
| `status` | enum | `analyzed` / `confirmed` / `materialized` / `conflict` |
| `confirmed_enum_value` | str | `confirmed`/`materialized` 必填非空；`analyzed` 必须缺席；`conflict` 可选（登记冲突编码） |
| `confirmed_level` | enum | 可选 `L1`/`L2`/`L3`；缺省继承 `proposed_level` |
| `confirmed_by` | str | `confirmed`/`materialized` 必填非空（协调 Agent 身份）；其余状态必须缺席 |
| `conflict_note` | str | `conflict` 必填非空；其余状态必须缺席 |
| `revision` | int | ≥1；同 `conclusion_id` 严格递增 |

**状态机与转换规则**（机械可判，非法转换 = `conclusions_illegal_transition`）：

```text
analyzed   → confirmed    （协调批准：补 confirmed_enum_value / confirmed_by [/ confirmed_level]）
confirmed  → materialized （必须有 ledger 条目指向该 conclusion 且匹配已核销 submission receipt）
analyzed | confirmed → conflict （编码冲突退回业务确认：conflict_note 必填）
conflict  → analyzed    （业务重新确认后以 revision+1 新版本回到 analyzed，confirmed_* 字段清空）
其余转换一律非法；materialized 为终态（变更走既有批次失败/删除合同，不在本门内）
```

**修订规则**（以新版本取代旧版本并保留历史）：同 `conclusion_id` 的新版本以 `revision`
严格递增取代旧版本；被取代版本必须先落 archive 文件；机械校验：当前 `revision` =
max(archive 同 id revision) + 1（有 archive 时，违反 = `conclusions_revision_regression`），
且当前版本与 archive 最高版本之间的状态转换合法。一致性校验：`materialized` 条目必须
有匹配的 ledger 条目（`conclusions_materialized_without_ledger`）；各状态的必填/禁填字段
如上表（`conclusions_invalid_status_fields`）。

**具体示例**（业务语义只出现在示例/fixture，不进产品代码与 prompt；对齐需求 008A 节的
`biz:PartShortage` / `mapping:DelayReason_PS`「缺料/PS」例子）：

`value-semantics/conclusions/analysis-conclusions.json`（当前版本）：

```json
{
  "schema_version": "r3-0-008b-analysis-conclusions/v1",
  "scenario_id": "industrial-service-v3",
  "maintained_by": "modeling",
  "entries": [
    {
      "conclusion_id": "ac-0001",
      "mapped_property": "https://example.org/ind3/biz#delayReason",
      "candidate_value": "缺料",
      "business_meaning_hypothesis": "工单延期归因为备件短缺的受控值；需参与延迟归因分类、规则与跨切片复用，建议一等语义节点表达",
      "evidence_refs": [
        "interview:q-delay-cause-01",
        "input:business-terms.md#延迟原因",
        "sample:work_order_delay_events.cause_code（仅证据，编码未确认）"
      ],
      "proposed_level": "L3",
      "blocking_unknowns": ["数据库实际编码未确认（访谈候选 PS/PART_SHORTAGE 待业务确认）"],
      "status": "confirmed",
      "confirmed_enum_value": "PS",
      "confirmed_level": "L3",
      "confirmed_by": "coordinator",
      "revision": 2
    },
    {
      "conclusion_id": "ac-0002",
      "mapped_property": "https://example.org/ind3/biz#workOrderStatus",
      "candidate_value": "已完成",
      "business_meaning_hypothesis": "工单终态受控值；仅需解释编码并支持 SQL 过滤，无分类/关系/规则/复用需求",
      "evidence_refs": ["interview:q-status-02"],
      "proposed_level": "L2",
      "blocking_unknowns": [],
      "status": "analyzed",
      "revision": 1
    }
  ]
}
```

`value-semantics/conclusions-archive/ac-0001.r1.json` 为同一 `conclusion_id` 的
revision 1 版本：`status="analyzed"`、无 `confirmed_*`/`conflict_note` 字段——演示
`analyzed → confirmed` 合法转换与历史保留。

### 3.4 阶段 3 最小槽位门（009 回填点）

- **artifact**：`workspaces/modeling-runs/<run-id>/stage3-neutral-graph/neutral-candidate.json`，
  schema `r3-0-008b-stage3-slot/v1`。
- **字段**（封闭集合）：`schema_version`、`scenario_id`（非空）、`produced_by`（非空，建模
  Agent）、`approved_by`（非空，协调 Agent——批准记录）、`candidate_artifacts[]`（非空列表，
  每项为 run workspace 内相对路径，逐项存在、非符号链接、无逃逸——复用 002 `_safe_gate_path`
  语义）、`deferred_contract`（字面量 `"R3.0-009"`）、`slot_note`（可空）。
- **门语义**：只校验产物存在与批准记录（存在、可解析、schema 匹配、`approved_by` 非空、
  `candidate_artifacts` 可达；且 §3.6b approvals 中存在对应 `stage3_slot` 记录——
  `stage3_approval_record_missing`）；**不校验候选内容、共性识别、关系提升**——详细合同归
  R3.0-009。`deferred_contract` 字段是显式回填点：009 细化后以登记修订替换该槽位 schema
  （先例：R3.0-006 M3 对 002 拓扑记录的 additive extension），本设计不预写任何 009 字段。
- **挂接（先决检查模型，评审 High-1 修订）**：staged 任务的 monitor 求值顺序为 staged
  检查 → topology 检查：槽位不合格时本 tick 以 `stage3_*` 反馈保持门 closed 并**跳过**
  拓扑检查——不置 `_multi_slice_gate_opened` latch、不调用 `close()`（002 的
  `candidate_platform_gate.close()` 会把 state.json 整体覆写为 `{state: closed,
  reason_code}`、丢失开闸身份，与 latch 的 early-return 组合后关闭的门无法按 002 逻辑
  重开；先决检查模型下门只有一次 closed→open 转移，与 002 语义一致）。槽位合格后 staged
  检查不再介入，002 拓扑检查函数本身零改动。诊断口径：槽位不合格期间门 state.json 的
  reason 仍是 prepare 期写入的 `topology_missing_artifact`，`stage3_*` 只存在于反馈与证据
  流——诊断不得把 state.json reason 当作唯一来源。

### 3.5 阶段 5 值分析时点门（fail-closed 阻断物化命令）

- **载体**：Runner-private capability `protocol_staged_submit_modeling_batch`（§3.6 统一
  描述；阶段 5/6 共用同一前置检查器，区别仅在 unlock 状态）。
- **机械条件**：批次不含枚举物化命令（`create_enum_meaning` / `update_enum_meaning` / 被
  引用为 L3 值节点的 `create_entity`）时照常放行——落实「与候选值无关的核心业务语义可以
  继续建模」；含枚举物化命令而 unlock 缺失或非 `materialize` 模式 → 拒绝
  `staged_value_materialization_locked`，受控值候选只能以分析结论 artifact 形态存在。
- **RDF 侧「不存在猜测产物」**：归 R3.0-008A 已交付的 G7/dry-run/apply 完整性校验与命令面
  白名单（008A 测试计划 B6 已验收）；008B 在此交界不重复建设、不重验。

### 3.6 阶段 6 物化时点门（capability 前置机械检查）

**唯一提交通路**：staged 任务的 `protocol_tools` 不含直连 `submit_modeling_batch`（任务
配置层收口，`enabled_tools` 随之收口；smoke 任务本就零提交），批次提交经 Runner-private
capability：

```json
{
  "operation": "protocol_staged_submit_modeling_batch",
  "batch": {
    "session_id": "bs-…",
    "client_batch_id": "cb-20260903-0001",
    "ontology_id": "ont-…",
    "idempotency_key": "idem-r3-0-008b-0001",
    "expected_workspace_version": "3",
    "mode": "apply_atomic",
    "lease_token": "…",
    "items": [
      {"command_kind": "create_entity",
       "payload": {"entity_id": "PartShortage", "name": "缺料", "description": "…"}},
      {"command_kind": "create_enum_meaning",
       "payload": {"enum_meaning_id": "DelayReason_PS",
                   "property_iri": "https://example.org/ind3/biz#delayReason",
                   "enum_value": "PS", "business_meaning": "缺料",
                   "semantic_value": "https://example.org/ind3/entity#PartShortage",
                   "schema_source": "…", "semantic_version": "1"}}
    ]
  },
  "value_traces": [{"command_index": 1, "conclusion_id": "ac-0001"}],
  "l3_nodes": [{"command_index": 0, "entity_id": "PartShortage",
                "semantic_value_iri": "https://example.org/ind3/entity#PartShortage"}]
}
```

`batch` 是 `submit_modeling_batch` 实参的逐字镜像，**信封以真实工具签名为准**
（`backend/app/mcp/tools/modeling_batches.py`：`session_id` / `client_batch_id` /
`ontology_id` / `idempotency_key` / `expected_workspace_version` / `items[]
[{command_kind, payload}]` / `mode ∈ {dry_run, apply_atomic}` / `lease_token`——
`apply_atomic` 必须携带 lease_token，由协议 Agent 经既有 build-session lease 流程取得；
验收用 `inspect.signature` 对照该签名，防止 fake 转发器掩盖信封错位）；`value_traces` /
`l3_nodes` 是 Runner 侧追溯附参，**不转发**（backend 载荷字段白名单
`ALLOWED_FIELDS` 不变——这是零 backend 改动的关键构造）。`idempotency_key` 与
`client_batch_id` 由 **Runner 在创建 durable intent 时生成并固定**（同一 intent 的全部
重试不变；协议 Agent 不自造——见下文提交完整性规则）。

**机械检查（确定性求值顺序，首个失败即拒绝，typed reason code 返回给协议 Agent）**：

1. **门状态**：平台 MCP 门非 open → `staged_gate_closed`（保证阶段 4 之前零提交）。
2. **载荷 schema**：`batch` 形状按 §3.6 真实信封镜像校验（缺 `idempotency_key` /
   `expected_workspace_version`、`items` 缺席或空、`apply_atomic` 缺 `lease_token` 等均
   拒绝）、`value_traces`/`l3_nodes` 字段闭合 → `staged_submit_schema_mismatch` /
   `staged_submit_unparsable`。
3. **unlock 前置**：commands 含枚举物化命令 → `value-semantics/unlock/materialization-unlock.json` 必须存在且
   `mode=materialize` 且自身校验通过（§3.6 unlock 合同）→ 否则
   `staged_value_materialization_locked` / `unlock_*`。
4. **create_enum_meaning 匹配**（按 `mapped_property`+候选值机械匹配）：
   - 必须有 `value_traces` 条目指向该命令（`staged_missing_trace`）；
   - 结论在**当前** analysis-conclusions 中存在（`staged_trace_mismatch` 的悬空形态）；
   - `status == confirmed`（`analyzed` → `staged_conclusion_not_confirmed`；`conflict` →
     `staged_conclusion_conflict`；`materialized` → `staged_conclusion_already_materialized`）；
   - `conclusion.mapped_property == payload.property_iri` 且
     `conclusion.confirmed_enum_value == payload.enum_value`（否则 `staged_trace_mismatch`）。
5. **update_enum_meaning 匹配**（backend update 载荷无 `property_iri`——
   `modeling_handlers.py` 约 309 行）：trace 条目必须显式携带 `mapped_property` 并等于
   `conclusion.mapped_property`；载荷含 `enum_value` → 必须 ==
   `conclusion.confirmed_enum_value`；载荷不含 `enum_value`（如仅加 `semantic_value` 做
   L2→L3 升级）→ 目标 `enum_meaning_id`/`enum_meaning_iri` 必须出现在既有已核销 receipt
   的枚举命令集合中且该命令 trace 到同一 `conclusion_id`（否则
   `staged_unknown_enum_target`）。
6. **L3 值节点**：payload `semantic_value` 非空 → IRI 必须 ∈ 本批 `l3_nodes` 声明的
   `semantic_value_iri` ∪ 已核销 receipts 登记的 L3 IRI（`staged_dangling_semantic_value`）；
   每个 `l3_nodes` 条目：对应 `create_entity` 命令存在于本批、对应结论 `confirmed` 且
   有效层级（`confirmed_level` 缺省取 `proposed_level`）为 `L3`（否则
   `staged_l3_unapproved`）。
7. **durable intent（转发前写入）**：机械检查全部通过后、转发调用前，Runner 先写
   `value-semantics/submission-intents/intent-<ordinal>.json`（schema
   `r3-0-008b-submission-intent/v1`：`schema_version`、`ordinal`（与 receipt 同源递增）、
   `idempotency_key`、`client_batch_id`、`session_id`、`mode`、逐命令 canonical digest、
   `value_traces`、`l3_nodes`、`status ∈ {submitted, receipted, unknown}`）。intent 落盘
   成功才允许转发——未写 intent 的转发路径不存在。
8. **转发**：经注入式 host **写转发器**（新增组件：仅服务本 capability 的注入式转发
   函数/类，**不复用** `McpReadForwarder`——后者绑定 `PLATFORM_PROXY_READ_TOOLS` 硬只读
   allowlist，对写工具直接拒绝；第一段测试用 fake）以协议 Agent 的 model key 原样调用
   `submit_modeling_batch`。转发结果二分：**明确失败**（backend 错误响应）→
   `staged_batch_forward_failed`（原始错误摘要透传，不吞不猜），intent 保持 `submitted`，
   修复后可安全重试（backend 幂等键不变）；**结果不可判定**（超时、连接中断、响应不可
   解析）→ intent 置 `unknown`，capability 返回 `staged_batch_forward_unknown`。backend
   侧 008A G7/R3.0-003 G2/G3/G5/G6 照常执行（结构最后防线）。
9. **未知结果的确定性恢复规则**：对 `unknown` intent，按固定顺序裁决：以
   `client_batch_id`/`idempotency_key` 查询平台批次清单与详情（既有 list/get 接口）——
   命中已存在批次 → 认领该批次、补写 receipt、intent 置 `receipted`（backend 幂等保证
   同键重放安全，不重复 apply）；确认未命中 → 允许以**同一幂等键**重试；清单亦不可达 →
   intent 保持 `unknown` 悬置，monitor 交叉校验发现悬置 intent → 门 kill-switch
   （`staged_unreconciled_batch`），人工裁决后重开。**禁止**在 unknown 未裁决前以新幂等键
   发起新提交（机械上：capability 在存在未裁决 unknown intent 时拒绝一切新提交）。
10. **回执**：成功 → Runner 写权威 receipt
   `value-semantics/submission-receipts/receipt-<ordinal>.json`（schema
   `r3-0-008b-submission-receipt/v1`：`schema_version`、`ordinal`（int，从 1 严格递增）、
   `intent_ordinal`、`idempotency_key`、`mode`、`batch_id`（非空）、`commands[]`（逐命令
   canonical digest）、`value_traces`、`l3_nodes`、`response_digest`、
   `submitted_via`=`protocol_staged_submit_modeling_batch`），并把对应 intent 置
   `receipted`。协议 Agent 不自报提交事实——receipt 是 Runner 权威记录。

**materialization-unlock 合同**（`r3-0-008b-materialization-unlock/v1`，协调 Agent 维护）：

| 字段 | 机械要求 |
| --- | --- |
| `schema_version` / `scenario_id` / `unlocked_by` | 常规非空；`unlocked_by` 为协调 Agent 身份 |
| `mode` | `materialize` 或 `skip` |
| `mapping_sources[]` | `materialize` 时非空；每项 `{source_type: database_schema \| interface, reference}`（`interface` 仅登记取值面，具体支持归 R3.0-010）；`skip` 时必须缺席 |
| `confirmed_codes[]` | 每项 `{conclusion_id, mapped_property, confirmed_enum_value, confirmed_level}`；必须与当前 conclusions 中 `confirmed` 条目逐字段一致（`unlock_code_mismatch`）、引用闭合（`unlock_dangling_conclusion`）；`skip` 时必须为空/缺席 |
| `skip_reason` | `skip` 时必填且恰为 `no_schema_no_interface`（`unlock_skip_inconsistent`）；`materialize` 时必须缺席 |

**skip 语义**（需求：既未提供数据库 Schema 也未提供接口信息时直接跳过本阶段）：`mode=skip`
是登记式终态——枚举物化命令在本次 run 内永久拒绝（`staged_value_materialization_locked`），
受控值保持 `analyzed` 分析结论（skip 下当前 conclusions 不得出现 `confirmed`/`materialized`
条目，`unlock_skip_inconsistent`），其余业务语义提交不受影响。

**编码冲突**：协调 Agent 判定实际编码与原分析冲突时，将结论置 `conflict`（新修订 +
`conflict_note`），capability 以 `staged_conclusion_conflict` 拒绝该候选值的物化，退回业务
确认（`conflict → analyzed` 新修订后重新走确认链）。不按列名或样例分布自动猜测——机械上
不存在任何自动改写结论状态的路径（状态推进只能由 Agent 修订 artifact 完成）。

**物化追溯链**（零 RDF 字段）：`analysis-conclusions（materialized 修订） ←
materialization-ledger（协议 Agent 应用清单） ← submission-receipts（Runner 权威回执） ←
平台批次 ID`。ledger 合同（`r3-0-008b-materialization-ledger/v1`，协议 Agent 维护）：

```json
{
  "schema_version": "r3-0-008b-materialization-ledger/v1",
  "scenario_id": "industrial-service-v3",
  "maintained_by": "protocol",
  "entries": [
    {"conclusion_id": "ac-0001", "receipt_ordinal": 1, "batch_id": "mb-…",
     "command_digest": "sha256:…",
     "semantic_value_iri": "https://example.org/ind3/entity#PartShortage"}
  ]
}
```

monitor tick 交叉校验：每条 ledger 条目必须匹配一个已核销 receipt 的 `apply_atomic` 枚举
命令（`receipt_ordinal`/`batch_id`/`command_digest` 三元组一致，`staged_ledger_stale`）；
`materialized` 结论必须有匹配 ledger 条目（§3.3）；每份 `receipted` intent 必须有同
`intent_ordinal` 的 receipt、不得存在未裁决的 `unknown` intent（悬置即 kill-switch，
`staged_unreconciled_batch`）。**平台批次对账**：纯函数
`reconcile_platform_batches(platform_batch_listing, intents, receipts)`——平台侧批次清单与
Runner intent/receipt 记录比对，出现不可对账批次（平台有而 intent 无 = 绕行直连；intent
`receipted` 而平台无 = 假回执）→ 门 kill-switch 关闭（`staged_unreconciled_batch`）并
按 `collaboration/routing` 层失败登记（第一段单测覆盖，第二段真实运行使用）。

### 3.6b 协调批准 artifact（`r3-0-008b-approvals/v1`，批准归属机械闭合）

批准身份必须锚定在 **coordinator 唯一写目录**，`confirmed_by`/`approved_by` 字符串只作为
展示信息、不再单独作为批准证据（否则建模 Agent 自填即可伪造协调批准）：

- **位置**：`workspaces/modeling-runs/<run-id>/value-semantics/approvals/approvals.json`，
  coordinator 唯一写（§3.9 bind 表），其余角色只读。
- **顶层字段**（封闭集合）：`schema_version`、`scenario_id`（非空）、`maintained_by`
  （非空，须为 coordinator 身份）、`entries[]`。
- **entry 字段**：`kind ∈ {conclusion_confirmation, stage3_slot}`、`target_id`（非空——
  `conclusion_confirmation` 时为 `conclusion_id`；`stage3_slot` 时为槽位标识）、`revision`
  （int ≥1，`conclusion_confirmation` 时必须等于被批准结论的当前 `revision`）、
  `confirmed_enum_value`（`conclusion_confirmation` 时必填，须与结论一致）、`approved_by`
  （非空）、`note`（可空）。
- **交叉校验（monitor tick，确定性）**：
  - conclusions 中 `status ∈ {confirmed, materialized}` 的每条条目必须有同
    `conclusion_id` + 同 `revision` 的 `conclusion_confirmation` approval → 否则
    `conclusions_approval_missing`；
  - stage3 槽位 artifact 的 `approved_by` 必须有对应 `stage3_slot` approval 记录 →
    否则 `stage3_approval_record_missing`；
  - unlock 的 `unlocked_by` 由 coordinator 唯一写目录天然锚定（unlock 本身在 coordinator
    bind 内），不另设 approval 条目。
- 修订语义：结论以新 revision 重回 `analyzed` 后，旧 approval 失效（revision 不匹配即
  缺失），再次确认需新 approval 条目——与 §3.3 修订规则同构。

### 3.7 阶段 7 联合验收清单 artifact（`r3-0-008b-joint-acceptance-checklist/v1`）

- **位置**：`workspaces/modeling-runs/<run-id>/joint-acceptance/joint-acceptance-checklist.json`；
  协调 Agent 汇总、Runner 结构校验。
- **字段**：`schema_version`、`scenario_id`、`produced_by`（非空）、`items[]`——七个**固定**
  `item_id` 各恰一条（缺失/重复/多余均 `acceptance_checklist_schema_mismatch`）：

| item_id | 对应验收内容 | 第一段机械面 |
| --- | --- | --- |
| `business_semantics_recall` | 业务语义召回 | 仅结构 |
| `commonality_recall` | 共性节点与关系召回（009 交界） | 仅结构 |
| `cross_slice_cross_ontology_recall` | 跨切片/跨 Ontology 召回 | 仅结构 |
| `value_semantics_recall` | 值语义召回 | 仅结构 |
| `sql_mapping_chain` | SQL 映射链 | 仅结构 |
| `r30008a_representative_question_recheck` | 008A 验收条件 3 代表问题「查询因为缺料而延期的订单」真实复验 | 仅结构；**真实复验明确归第二段** |
| `rdf_no_business_rows` | RDF 未复制客户、设备、工单等业务行 | 仅结构；真实断言归第二段 |

  每条 item：`item_id`、`verdict ∈ {pass, fail, pending}`、`evidence_ref`（非空）、
  `checked_by`（非空）。
- **第一段门**：monitor 在 staged 任务终态前要求该 artifact 存在且结构合格（不合格 →
  typed 反馈，不接受终态）；**不判定 verdict 真伪**。`pass` 的语义成立只能由第二段真实
  运行联合验收声明——测试计划显式排除第一段宣称。

### 3.8 角色职责增量与 prompt 落点（描述性，零业务语义）

只写角色、时点义务与拒绝行为；业务语义、具体编码、具体问题不进 prompt（平台/参考本体
边界）。三处各一节「Staged modeling decisions (R3.0-008B)」，紧随既有
「Multi-slice workflow (R3.0-002)」节（`agent-packages/{coordinator,modeling,protocol}/
instructions.md`，行位约 138/296/613 之后）：

- **modeling**：当任务声明 `staged_modeling_decisions`，在基础业务语义建模期间把经常出现、
  数量可控、近似受控枚举的候选值逐条登记进分析结论 artifact（假设、证据、建议层级、阻塞
  未知）；不因看到数据库样例值就自行确认含义；修订以新版本取代旧版本并保留历史；仍只拥有
  业务语义，不拼装平台协议参数。
- **coordinator**：批准结论状态推进（仅在编码经业务确认后 analyzed→confirmed；冲突置
  conflict 退回业务确认），并在自身独占 approvals artifact（§3.6b）中同步登记批准记录；
  维护 materialization-unlock（含 skip 登记形态）；汇总阶段 7 checklist；把 staged 门的
  typed reason code 当作修复指令——修 artifact，绝不要求任何
  角色对关门重试平台调用；仍绝不直接调用平台写接口。
- **protocol**：当任务声明 `staged_modeling_decisions`，一切 Modeling Batch 提交只经
  Runner-private capability `protocol_staged_submit_modeling_batch` 并携带追溯附参
  （`value_traces`/`l3_nodes`）；维护 materialization-ledger 应用清单；只翻译获批结论——
  不自行把 L2 升为 L3、合并语义节点或补猜编码；capability 返回 typed 拒绝时按 reason code
  修复 trace/通知协调 Agent 修 artifact 后重试，绝不绕行直连提交。

任务 objective 与 references 合同（`r3-0-008b-staged-decisions-contract.json`）承载其余
机械描述（artifact 位置、schema、reason code 全表），先例 002 §9 裁决 3。

### 3.9 零 backend 改动论证

1. **检查位置**：阶段 5/6 物化门是对**批次提交的前置机械检查**，全部发生在 modeling_team
   侧（capability handler 在 host 进程内、读取 run workspace artifact、消费 Runner 侧追溯
   附参），backend 的 `submit_modeling_batch` 收到的载荷与直连调用逐字节相同。
2. **backend 完整性校验不动**：008A 交付的 G7（`semanticValue` 结构门、悬挂保护）与
   R3.0-003 G2/G3/G5/G6 继续作为 dry-run/apply 结构最后防线；008B 不新增、不修改、不绕过
   任何 backend 校验，`ALLOWED_FIELDS` 白名单不变（追溯附参不进 backend 载荷）。
3. **通路收口的机械面**：staged 任务 `protocol_tools` 省略直连 `submit_modeling_batch`
   （`enabled_tools` 随任务配置收口，`protocol_mcp_launch.py` 既有机制零改动）；capability
   广播面由任务参数分派（非 staged 任务不广告该操作）；host 转发先例已验收
   （`modeling_readonly.py` `_forward` 注入 + 请求/响应/回执摘要三联）。
4. **存储**：全部 artifact 在 repo-local 共享运行目录（`workspaces/modeling-runs/<run-id>/`，
   gitignored），不进 backend 表/RDF；无 migration、无新 API 路由、无新 MCP 工具、
   `SAFE_PROTOCOL_TOOLS` 字节不变。
5. **staged artifact 可写通路（评审 High-2 修订）**：当前 codex 沙箱中仅 coordinator 被提升
   为 `workspace-write` 且其可写 bind 只有 `run_root/scenario-map` 一个目录，其余角色对
   run root 连读挂载都没有（`_thread_sandbox` / `_coordinator_scenario_map_bind`）。staged
   任务必须逐角色增加定向可写 bind（复用同一先例），唯一写者约束：

   | 目录/文件 | 唯一写者 | 说明 |
   | --- | --- | --- |
   | `value-semantics/conclusions/` + `value-semantics/conclusions-archive/` | modeling | 分析结论与修订历史 |
   | `stage3-neutral-graph/` | modeling | 009 槽位 artifact |
   | `value-semantics/unlock/`、`value-semantics/approvals/`、`joint-acceptance/` | coordinator | unlock 登记与验收清单汇总；approvals 为协调批准权威记录（§3.6b） |
   | `value-semantics/ledger/` | protocol | 应用清单 |
   | `value-semantics/submission-receipts/`、`value-semantics/submission-intents/` | Runner（host 侧） | 权威回执与 durable intent，不经沙箱 bind |

   **bind 单元是目录而非文件**（评审 High-3 修订）：可选单文件 artifact（unlock/ledger/
   conclusions）各住角色独占子目录，prepare 期只 `mkdir`、不预创建任何文件——「文件缺席」
   即门语义（unlock 缺席 → `staged_value_materialization_locked`；conclusions 缺席 →
   `staged_conclusions_unavailable`），占位文件会把 reason code 漂移成 `*_unparsable`/
   `*_schema_mismatch` 甚至形成合法形态绕过阶段 5 锁，因此禁止；目录 bind 同时使唯一写者
   约束机械成立（bwrap `--bind` 要求源路径在 namespace 创建时已存在，且规避文件级 bind 的
   原子替换/陈旧 inode 问题）。三角色对 `value-semantics/` 树互相只读可见（只读 bind）；
   非写者对上述目录无写通路。
   该扩展只对 staged 任务生效，非 staged 任务的沙箱与 bind 配置字节不变（F1 守恒）。
6. **已知残余面（登记不修）**：沙箱内协议 Agent 名义上可及 `http://127.0.0.1:8001` 与
   自身 key，直连 HTTP 绕行在物理上未被阻断。缓解 = 任务工具面收口 + prompt 拒绝义务 +
   `reconcile_platform_batches` 对账 + 门 kill-switch（`staged_unreconciled_batch`）。该
   威胁模型与 R2.3/R3.0-002 一致（Agent 是有边界受信协作者，不是对抗主体）；若第二段真实
   运行发现绕行证据，按窄失败层登记并只修该层。

### 3.10 与其他需求的边界

| 需求 | 交界合同 |
| --- | --- |
| R3.0-008A | 映射资源合同、`semanticValue`、G7、「RDF 无猜测产物」机械校验全部归 008A（已验收）；008B 只做时点/产物/批准关系，交界处零重复建设（需求原文：不得互相推诿或重复建设）。008A 证据不得追溯解释为 008B 联合验收，反之亦然 |
| R3.0-009 | 阶段 3 为最小槽位门（存在性 + 批准记录）；`deferred_contract="R3.0-009"` 是显式回填点；008B 真实任务条目注明 009 机械增量完成前不得启动；checklist `commonality_recall` 项的详细验收归 009 专项 |
| R3.0-006 | 第二段真实运行挂 006 modeling start 授权体系与 attempt 预算；第一段零 attempt 消耗；真实任务条目复用 002 已登记的 `preview_baseline`/`baseline` 加载分派注意事项（该两处分派仍归 006 真实 run 前完成门） |
| R3.0-010 | unlock `mapping_sources.source_type` 预留 `interface` 取值面（仅登记）；接口映射源具体合同零实现 |

### 3.11 当前最小范围 vs 未来产品化

- **当前最小**：§3.1 表列 9 项增量 + 共享测试计划第一段机械验收；结论/解锁/回执/账本均为
  repo-local 人类可读 JSON；capability 转发器为注入式最小实现（第一段以 fake 覆盖单测）。
- **未来产品化（不得静默晋升入完成门）**：阶段门平台化存储与 UI、结论版本治理/不可变审计、
  多源编码冲突通用模型、自动 L2↔L3 升降级建议、物化批次自动回滚、跨 run 结论迁移、
  checklist verdict 自动采集。第二段（真实运行联合验收）不是产品化项，而是本需求的验收
  组成部分，但明确不在第一段完成门内。

## 4. 错误与边界

### 4.1 确定性 reason codes 全表

- 002 既有 `map_*` / `topology_*` / `suggestions_*`：零改动复用。
- 阶段 3 槽位：`stage3_missing_artifact` / `stage3_unparsable` / `stage3_schema_mismatch` /
  `stage3_missing_approval` / `stage3_candidate_artifact_unavailable`。
- 结论 artifact：`conclusions_unparsable` / `conclusions_schema_mismatch` /
  `conclusions_invalid_status_fields` / `conclusions_illegal_transition` /
  `conclusions_revision_regression` / `conclusions_materialized_without_ledger` /
  `conclusions_approval_missing`（§3.6b）/ `approvals_unparsable` /
  `approvals_schema_mismatch`。
- unlock：`unlock_unparsable` / `unlock_schema_mismatch` / `unlock_code_mismatch` /
  `unlock_dangling_conclusion` / `unlock_skip_inconsistent`。
- capability 提交门：`staged_gate_closed` / `staged_submit_unparsable` /
  `staged_submit_schema_mismatch` / `staged_conclusions_unavailable` /
  `staged_value_materialization_locked` / `staged_missing_trace` /
  `staged_conclusion_not_confirmed` / `staged_conclusion_conflict` /
  `staged_conclusion_already_materialized` / `staged_trace_mismatch` /
  `staged_unknown_enum_target` / `staged_l3_unapproved` / `staged_dangling_semantic_value` /
  `staged_batch_forward_failed` / `staged_batch_forward_unknown` /
  `staged_ledger_stale` / `staged_unreconciled_batch`。
- 阶段 7：`acceptance_checklist_missing` / `acceptance_checklist_unparsable` /
  `acceptance_checklist_schema_mismatch`。

全部失败可自愈（fail-closed 不杀 run）：修复 artifact / trace / ledger 后重试 capability
或等待下一 monitor tick 重评；`staged_unreconciled_batch` 例外——按协作路由层失败登记，
修复需人工裁决后重开。

### 4.2 已记录边界（不修，不判 FAIL）

- `delete_enum_meaning` 与已物化 L3 节点删除不在物化门触发集合内（物化只发生在 confirmed
  之后；删除/回滚走既有批次失败合同与 008A 悬挂保护）。
- 结论的 `evidence_refs` 只做非空格式校验，不做证据登记表闭合（002 保护建议同款口径）。
- `business_meaning` 与 `candidate_value` 措辞一致性不机械仲裁（匹配键是
  `mapped_property`+`confirmed_enum_value`，不是自然语言）。
- 直连 HTTP 绕行面（§3.9 第 5 条）按登记边界处理。
- checklist `verdict` 真伪、七项语义成立性：第二段范围。
- `create_table_mapping` / `create_join_mapping` 不在物化门触发集合内：其来源（输入包
  schema.sql 的表/列定义）本身是已确认输入，本门防的是「编码/值域猜测物化」；若第二段
  真实运行证伪该边界，再以登记修订纳入 unlock 触发集。
- 阶段 5 的「提前创建正式 L3 值节点」拦截依赖 protocol Agent 在 `l3_nodes` 附参中如实
  声明：不含枚举命令的批次携带未来才用作 L3 的裸 `create_entity` 不被机械识别（后续
  `semanticValue` 链接会被 `staged_dangling_semantic_value` 拒绝，但裸实体可能已写入
  RDF）；第二段独立验收须以「RDF 实体集对照 confirmed 结论集」的真实审计补足该断言。

### 4.3 平台/参考本体边界

「缺料」/`PS`/`PartShortage` 等领域名称只出现在本设计示例、fixture、问句与断言；新增
产品代码（`staged_decisions.py`、capability handler、prompt 节）只含机械规则与通用字段名，
无领域分支（测试计划 grep 门 F4）。

## 5. 发布影响

- 改动全部在 `modeling_team/`（6 个新文件 + 6 个文件的增量，附录 A）；backend/frontend 零
  diff → 无 migration、无服务重启需求。若触发窄修复例外：按 CLAUDE.md 全量 pytest →
  `systemctl --user restart ontology-platform.service` → 健康检查，并在实现记录显式论证。
- 回归：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests -q` 全绿（002 后基线之上不新增失败）+ `uv run --project backend ruff
  check modeling_team`；backend 全量 pytest 确认零 diff。
- 对 002/006 及既有 formal 任务零影响：无 `staged_modeling_decisions` 参数时全部新代码路径
  不激活（守恒测试）；`SAFE_PROTOCOL_TOOLS` 字节不变；capability 广播面按任务参数分派。

## 6. 验收标准（第一段；详见共享测试计划）

| ID | 标准 |
| --- | --- |
| A1 | 配置与合同资产存在且符合：新模块/references 合同/两个任务条目/profile 复用通过 validate CLI；`parameters` 扩展与依赖约束（staged 必须伴随 multi_slice）生效 |
| A2 | 结论 artifact 合同：合法 fixture（含 §3.3 示例）通过；违约 fixture（字段漂移/非法状态字段/非法转换/修订回退/materialized 无 ledger/confirmed 无 approval 记录）确定性拒绝且 reason code 确定；§3.6b approvals 合同与交叉校验（结论与 stage3 槽位两侧）行为确定 |
| A3 | unlock 合同：materialize/skip 两形态合法 fixture 通过；编码不一致、悬空引用、skip 形态含 confirmed 条目等确定性拒绝 |
| A4 | 阶段门行为：stage3 槽位先决门拦截/放行（不合格时拓扑检查不执行、latch 不置位、state.json 不被覆写；修复后开闸一次）；capability 全部拒绝路径（§4.1 staged_* 全表）逐条触发且 reason code 确定；提交信封与 backend `submit_modeling_batch` 真实签名对照（`inspect.signature`）一致；合法追溯 + fake 转发通过并按序写 intent→receipt；unknown intent 的认领/同键重试/悬置 kill-switch 三分支行为确定；ledger 交叉校验与平台对账函数行为确定 |
| A5 | 守恒与回归：无参数任务零行为变化；`SAFE_PROTOCOL_TOOLS` 不变；非 staged 任务不广告新 capability 操作；modeling_team 全量 pytest 绿、backend 零 diff |
| A6 | smoke 任务条目机械链路可走通（零 Modeling Batch、零 dry-run、零 apply、零 RDF 写、零 Build Session/Lease/attempt） |
| A7 | 修订与历史：supersede + archive 链条机械成立（新版本取代、历史保留、转换合法性跨版本校验） |
| A8 | 两段边界显式：第一段不宣称联合验收闭环、008A 代表问题真实复验、RDF 真实断言（测试计划显式登记为第二段范围）；008A/009/010/006 交界零越界 |

## 7. 假设（错误则需重设计）

1. **任务工具面收口足以承载唯一提交通路**：staged 任务 `protocol_tools` 省略
   `submit_modeling_batch` 后，`enabled_tools` 收口由既有 launch 机制保证；残余绕行面按
   §3.9 第 5 条登记并由对账 + kill-switch 兜底。若第二段发现绕行不可接受，需重设计为
   backend 侧命令级校验（届时属 backend 增量需求，需用户确认）。
2. **host 转发器可复用注入模式**：`McpReadForwarder`/`ModelingReadProxy._forward` 先例可
   扩展为写路径转发（同一 model key、同 digests 三联）。若平台写面对 host 转发有未预期
   合同（如 lease token 绑定进程），capability 转发实现需窄调整，不影响门合同本身。
3. **`update_enum_meaning` 目标回溯充分**：不带 `enum_value` 的 update 可经「既有已核销
   receipt 的枚举命令集合」闭合追溯。若真实运行出现既有枚举（非本 run 物化）需要 update
   的场景，需扩展 unlock 合同登记存量目标（登记修订，不破坏 schema）。
4. **monitor tick 频率满足自愈节奏**：stage3/checklist/ledger 校验均为 tick 级重评，与 002
   拓扑门同节奏；无实时性要求。

## 附录 A 新增/修改文件清单（预期路径，供开发冻结）

新增：

1. `modeling_team/staged_decisions.py` — 纯机械模块：schema 常量、目录/文件名常量、loader
   （符号链接/逃逸拒绝）、`validate_analysis_conclusions`（含状态字段/转换/修订/archive 链）、
   `validate_materialization_unlock`、`validate_approvals`（§3.6b）及其与 conclusions /
   stage3 槽位的交叉校验、`validate_stage3_slot`、
   `validate_joint_acceptance_checklist`、`validate_staged_submission`（§3.6 全部匹配规则，
   输入为载荷 + artifact 快照 + 既有 receipt 索引）、submission intent 读写/状态迁移与
   unknown 裁决纯函数、`validate_materialization_ledger`、
   `reconcile_platform_batches(platform_batch_listing, intents, receipts)`、reason codes
   全表常量。
2. `modeling_team/references/r3-0-008b-staged-decisions-contract.json` — Agent 可读合同
   （artifact 位置、schema、状态机、reason code 全表、capability 用法）。
3. `modeling_team/tasks/r3-0-008b-staged-decisions-smoke.yaml` — 机械 smoke（设计 §6/A6、
   测试计划）。
4. `modeling_team/tasks/r3-0-008b-staged-real.yaml` — 真实分阶段任务条目（冻结资产；头部
   注明双重门：009 机械增量完成 + 006 用户授权；role_sources 沿 002 真实任务白名单 +
   008B 合同；protocol_tools 省略 `submit_modeling_batch`）。
5. `modeling_team/tests/test_r30008b_staged_decisions.py` — artifact 合同单测。
6. `modeling_team/tests/test_r30008b_runner_wiring.py` — 门接线/capability/守恒测试。

修改：

7. `modeling_team/contracts.py` — `STAGED_MODELING_DECISIONS_PARAMETER`（`parameters` 封闭
   键集扩展，boolean，依赖 `multi_slice_workflow`）+ 守恒校验。
8. `modeling_team/capability_mcp.py` — `STAGED_PROTOCOL_OPERATIONS`（=
   `PROTOCOL_OPERATIONS + ("protocol_staged_submit_modeling_batch",)`）与操作 schema/分派。
9. `modeling_team/runner.py` — drain tick 中 `_check_staged_decision_gates()` 在
    `_check_multi_slice_topology_gate()` **之前**执行（stage3 先决
   门、checklist 终态门、approvals 交叉校验、ledger/receipt/intent 交叉校验、
   kill-switch）；capability handler（校验 → durable intent 写入 → **新增 host 侧写
   转发器**调用（注入式，仅服务本 capability，不复用只读 `McpReadForwarder`/
   `PLATFORM_PROXY_READ_TOOLS` allowlist）→ receipt 写入 → intent 状态迁移 → 审计日志）；
   staged 任务的 capability 广播分派与
   反馈投递（kind=`staged-decision-gate`，fingerprint 去重集合与 002 拓扑门反馈
   各自独立，避免每 tick 重复投递）。
10. `modeling_team/acceptance.py` — `RunnerCapabilityEndpoint` 的 operations 集合组装处：
    staged 任务加入 `protocol_staged_submit_modeling_batch`（按任务参数分派，非 staged
    端点 operations 集字节不变）。capability 端点的 role→operations 映射与广播面在该文件
    组装，本项接线缺失则协议 Agent 在 staged 任务中没有合法提交路径。
11. `modeling_team/runtimes/codex.py` — staged 任务向协议 Agent 广告 staged capability 操作
    （按任务参数分派，含非 formal multi-slice run 的广告谓词扩展——注意不波及
    `_coordination_enabled` 关联的 turn binding/provider session 面；gate 两处谓词零改动
    ——staged 蕴含 multi_slice，既有条件已覆盖）；staged 任务逐角色新 artifact 目录可写
    bind（§3.9 第 5 条 bind 表；非 staged 任务 bind 集字节不变）。
12. `modeling_team/agent-packages/coordinator/instructions.md`、
    `modeling_team/agent-packages/modeling/instructions.md`、
    `modeling_team/agent-packages/protocol/instructions.md` — 各一节
    「Staged modeling decisions (R3.0-008B)」（§3.8）。

零改动声明：`backend/**`、`frontend/**`、`modeling_team/profiles/`（复用
`r3-0-002-modeling-team.yaml`）、`SAFE_PROTOCOL_TOOLS`、002 既有 artifact schema 与
`scenario_map.py` 校验函数。
