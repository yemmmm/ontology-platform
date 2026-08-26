# R3.0-002 完整场景多切片建模流程 — 功能设计

- 日期：2026-08-26
- 状态：已实现（2026-08-26）；计划评审 3 轮（Round 1/2 REVISE 处置见 §10/§11，Round 3
  PASS）；共享测试计划独立 Round 1 PASS
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-002（含 §2 已确认原则 4/5/6/10、
  §3.2 逻辑建模切片表、§5 能力差距）
- 冻结边界：`docs/delivery/designs/2026-08-25-v3-0-remaining-requirements-outline-design.md`
  §3（R3.0-002）、§1 依赖链、§2 共享原则
- 共享测试计划：
  `docs/delivery/test-plans/2026-08-26-r3-0-002-multi-slice-modeling-workflow-test-plan.md`
- 交付边界：R2.3 Team Runner + 三 Agent 包（coordinator/modeling/protocol）基线上的
  v3.0 多切片增量；**默认零 backend 表/API/migration 改动**（仅在发现真实缺口时允许窄修复
  并显式论证）；验收只做确定性/机械验证（循 R2.3-001 先例），不启动真实 modeling start、
  不消费建模 attempt 预算、不验收语义质量（归 R3.0-006）

## 1. 目标

1. 一个完整业务场景（工业售后 v3，输入包
   `docs/evaluation-scenarios/industrial-service-v3/modeling-input/`）可被拆成多个有界逻辑切片
   （S1–S5 起步）协调建模、复核与整合，过程保留项目级全局视图，而非把五个切片当成互不
   相关的独立任务，也不是把完整场景压成一个简单切片。
2. 首次真实 apply 前存在**机械强制的拓扑决策门**：比较至少三个方案（单 Ontology / 按领域
   多 Ontology / 共享核心+领域 Ontology）× 六个固定维度（概念内聚、关系密度、复用、权限
   边界、变更节奏、跨域查询）；门只做存在性与覆盖检查，不评判内容优劣。
3. 多 Ontology 拓扑可按"每 Ontology 至少一个批次、按场景地图依赖顺序"机械执行；项目级
   整合视图复用现有 project scope 语义检索，无跨批次原子性要求。
4. 建模流程产出**建议保护语义资源 IRI 清单**（明确 IRI + 理由），由平台协议 Agent 经现有
   R3.0-004 保护集 MCP/HTTP 接口（model scope）执行；保护集变更与本体发布是两个独立操作。
5. 三角色职责边界不变；确定性机械（ID、发布、重试、解析、门的存在性检查）留在 Runner/工具侧。
6. 交付本身可被确定性验证：资产合同存在且符合、Runner 门机制按合同行为、空/测试作用域
   smoke 可走通多切片机械链路。

## 2. 非目标

1. 不做切片并行执行、不规定每切片 Agent 数量（默认串行 S1→S2→S3→S4→S5）。
2. 不做拓扑决策评分公式自动化（决策内容由 Agent 语义判断）。
3. 不做中间产物的最终 schema/UI，不把场景地图存入平台（它是 run workspace 内人类可读
   artifact，流程输入/中间产物）。
4. 不做自动重试与长期调度、多项目协作。
5. 不新建专用跨切片一致性引擎、不做自动术语合并。
6. 不新增平台产品化能力：默认零 backend 表/API/migration/前端改动。
7. 不启动真实建模（R3.0-006）、不消费建模 attempt 预算、不验收语义模型质量。
8. 不实现 R3.0-003 的映射合同细节与 R3.0-005 的 SQL 链路，只预留衔接点（切片候选内可含
   映射占位，合同归 R3.0-003）。
9. 不把"先保护目标 IRI 再创建资源"变成平台硬校验；不要求保护集变更与本体发布同批次。

## 3. 功能合同

### 3.1 交付形态与复用基线（current minimal scope）

按 L0"复用最近已验收基线"规则，完整复用 R2.3 Team Runner 基线（`modeling_team/runner.py`、
`contracts.py`、`candidate_platform_gate.py`、`candidate_publication.py`、
`agent-packages/{modeling,coordinator,protocol}`、`profiles/`、`tasks/`、`references/`、
`tests/`），只实现以下增量（字段与接线点见附录 A）：

| # | 增量 | 性质 |
| --- | --- | --- |
| 1 | `modeling_team/scenario_map.py` | 新小模块：场景地图 artifact 合同 loader + 结构校验 + 拓扑决策记录合同与门检查（纯机械） |
| 2 | `modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml` | 新机械 smoke 任务（零建模写，见测试计划） |
| 3 | `modeling_team/tasks/r3-0-002-multi-slice.yaml` | 新 v3.0 真实多切片任务配置（role_sources 白名单挂载 v3 输入包 4 个 allowed_files；R3.0-006 用户授权前不得启动） |
| 4 | `modeling_team/profiles/r3-0-002-modeling-team.yaml` | 新三 Agent roster（coordinator/modeling/protocol；acceptance 归 R3.0-006）；经增量 6 的非 formal 加载通路加载 |
| 5 | `modeling_team/references/r3-0-002-scenario-map-contract.json` | 新 Agent 可读 artifact 合同（挂载给三角色，先例 `platform-neutral-candidate-authoring.json`） |
| 6 | `modeling_team/contracts.py` + 加载分派增量 | (a) 新增 `SAFE_PROTOCOL_TOOLS_R30002 = SAFE_PROTOCOL_TOOLS ∪ {6 个保护集工具}`（循 `SAFE_PROTOCOL_TOOLS_R23003` 先例，`SAFE_PROTOCOL_TOOLS` 字节不变）；(b) 新增非 formal 的 `multi_slice` profile 加载通路：strict 加载仍强制四角色（`contracts.py:413-419`），为 v3.0 profile 显式开放"恰 coordinator/modeling/protocol 三角色"的校验分支，并让 CLI `validate` 与 `TeamRunner.prepare()` 按 profile kind 分派（`__main__.py:535`、`runner.py:388` 现仅走 strict）。注：`runner.py:1221 preview_baseline` 与 `__main__.py:501 baseline` 命令仍走 strict，本次交付（validate + 单元级 smoke）不经过它们；R3.0-006 启动真实 run 前须补该两处分派（届时为完成门项，本次预留注明）；(c) task schema 扩展：v2 Task 字段集为封闭等值校验（`v2_fields`/`v2_fields_with_binding`），新增 `parameters` 键须扩展冻结 schema 并配守恒测试 |
| 7 | `modeling_team/runner.py` + `runtimes/codex.py` 门机制增量 | 任务参数 `multi_slice_workflow: true` 触发**独立平台 MCP 门**（不依赖 formal receipt 管线）：runner 为该类任务创建门并登记 v3.0 场景地图/交接物 canonical 路径；拓扑门检查通过后开闸。**gate 全链路条件必须统一为一个谓词并同时覆盖两处**（计划评审 High-4 证实为两个独立条件源）：MCP env 传参点（`runtimes/codex.py:3641-3652` `_candidate_platform_gate_enabled_for_run()`）**和**沙箱挂载点（`codex.py:3014-3020` `self._candidate_platform_gate_enabled` 赋值 / `codex.py:4024-4036` bind-mount 块，现派生自 `_is_formal_acceptance_run`）；两处均扩展为"`formal_acceptance` 或 `multi_slice_workflow`"。只扩一处会导致沙箱内 state 文件不可达、后端 MCP 全部平台调用 fail-closed 死锁（`backend/app/mcp/runtime.py:397-420`）。接线测试必须断言两处条件对 `multi_slice_workflow` 任务**同时为真**、对既有任务同时为假。既有 formal 开闸路径（`runner.py:3454` 一线）不动 |
| 8 | agent-packages 指令最小增量 | 优先放 task objective 与 references 合同；共享 `instructions.md` 只加最少必要段落（coordinator：维护场景地图、汇总保护 IRI 建议；protocol：按序多批次与保护集调用；modeling：按切片产出候选并申报共享术语） |

**平台零改动声明**：本需求默认不新增 backend 表/API/migration/前端。机械事实已验证：
一个 Modeling Batch 绑定一个 Ontology（`backend/app/repositories/models.py:268`
`ontology_id` 非空）、保护集 MCP 工具已存在（`backend/app/mcp/tools/protection_sets.py`，
model scope）、单 Project 多 Ontology CRUD 已存在。若实现中发现真实缺口，只允许窄修复，
须在设计文档追加论证并按 CLAUDE.md 全量回归 + 服务重启。

### 3.2 场景地图（scenario map artifact）

- **维护者**：建模协调 Agent（在 Runner run workspace 内维护）。
- **位置**：`workspaces/modeling-runs/<run-id>/scenario-map/scenario-map.json`（+ 可选人类
  可读 `scenario-map.md` 视图，非验收对象）。它是流程输入/中间产物，**不是平台存储**。
- **内容合同（固定六节，字段见附录 A.2）**：
  1. 切片清单（S1–S5 起步，允许流程内调整；调整须在 `adjustments` 数组留痕）；
  2. 共享术语注册表：术语 → 使用切片集合 → 唯一 owner 切片；
  3. 跨切片依赖：方向 + 连接点；
  4. 每切片所有权（归属建模执行单元）；
  5. 跨切片 competency questions；
  6. 显式未知项。
- **机械结构不变量**（Runner/工具检查，不评判内容）：schema_version 匹配；六节键齐备；
  引用闭合（依赖端点、术语 owner、CQ spans 均落在切片清单内）；每个共享术语恰一个 owner
  切片。显式未知项数组允许为空（内容充分性是语义质量问题，归协调 Agent 与 R3.0-006）。

### 3.3 拓扑决策门

- **时机**：首次真实 apply 前。机械映射：`multi_slice_workflow: true` 的任务中，平台协议
  Agent 的平台 MCP 调用由**独立平台 MCP 门**约束（复用 `candidate_platform_gate.py` 的门
  机械，state schema 仍为 `r2-3-005-candidate-platform-gate/v1`，后端零改动；但开闸条件
  不是 formal 候选 receipt，而是拓扑门检查通过）。**closed 期间全部平台调用被拒（含
  `get_project_build_context` 等读工具，循 formal 门先例，`runtime.py:477` 在读写豁免之前
  返回）；这不是回归**。计划评审已证实 formal
  candidate gate 只对注册进 `FORMAL_RUN_CONTRACTS` 的正式 run 创建（`formal_runs.py:95-101`），
  开闸点位于 formal acceptance receipt 路径（`runner.py:3424-3454`），对 v3.0 三角色任务不可
  达——因此本需求为多切片任务建立独立门，不注册 formal 合同、不引入 acceptance 角色（概要
  设计 §2.4 三角色边界）。门失败不改动既有任务的任何行为（无该参数即无此门）。
- **决策记录 artifact**：`workspaces/modeling-runs/<run-id>/scenario-map/topology-decision.json`
  （字段见附录 A.3）：至少三个方案且必须含三个规定 `option_id`
  （`single_ontology` / `domain_ontology_split` / `shared_core_plus_domain`，允许追加自定义
  方案）；每方案对六个固定维度（`concept_cohesion` / `relation_density` / `reuse` /
  `permission_boundary` / `change_cadence` / `cross_domain_query`）逐一非空评估；
  `selected_option` ∈ 方案集合；`rationale` 非空。
- **门语义（纯机械存在性/覆盖检查，不评判内容优劣）**：artifact 存在、可解析、
  schema_version 匹配、方案数 ≥3 且含三个规定 id、每方案六维度键齐且值非空、选择与理由
  非空。任一不满足 → 独立平台 MCP 门保持关闭（fail-closed，typed 确定性错误，见 §5）。
- **语义层约束（不由门检查）**：比较维度是概念内聚、关系密度、复用、权限边界、变更节奏、
  跨域查询，不是表数量或团队数量——该约束写入 references 合同与任务 objective，由
  R3.0-006 验收复核。
- **T0 防御复核**：该门保护的不变量（首次 apply 前存在显式拓扑决策）由需求与用户确认真实
  存在；失败后果可控且可自修复（Agent 补齐 artifact 后重试开闸，不杀 run、不产生不可恢复
  硬拒绝），符合仓库 T0 规则，予以保留。

### 3.4 多 Ontology 机械事实与多批次执行

- 一个 Modeling Batch 绑定一个 Ontology（`ontology_id` 非空，models.py:268）。多 Ontology
  拓扑 = **每 Ontology 至少一个批次**，由平台协议 Agent 按**场景地图依赖顺序**逐 Ontology
  应用；`dry_run` → `apply_atomic` 照旧；Build Session / Lease 机制照常按 Ontology 使用。
- **无跨批次原子性要求**：依赖顺序 + 每批次独立原子即合同；单批次失败按既有批次失败合同
  处理，不引入跨批次回滚。
- **项目级整合视图**：复用现有 project scope 语义检索（如 `query_semantic_context` 的
  project/多-ontology scope 与项目级读模型），不新增跨 Ontology 聚合 API。

### 3.5 保护 IRI 建议交接

- **交接物**：`workspaces/modeling-runs/<run-id>/scenario-map/protection-iri-suggestions.json`
  （协调 Agent 汇总；条目 = 明确绝对 IRI + 非空理由 + 提出切片 + 目标保护集标识，字段见
  附录 A.4）。机械上只校验格式，不评判保护决定。
- **执行**：平台协议 Agent 用现有 R3.0-004 保护集 MCP 工具（`list_semantic_protection_sets`、
  `create/update/delete_semantic_protection_set`、`add/remove_semantic_protection_set_members`，
  model scope，以 `backend/app/mcp/tools/protection_sets.py` 实名为准）
  执行；六个工具加入 `SAFE_PROTOCOL_TOOLS_R30002`，按 v3.0 任务选择。
- **顺序与独立性**："先保护目标 IRI 再创建资源"是**流程推荐顺序**（保护集允许悬空 IRI），
  不是平台硬校验；保护集变更与本体发布是两个独立操作，不要求同一 Modeling Batch；保护集
  Project 级、可跨 Ontology，不能反向驱动 Ontology 拆分（语义约束，归协调 Agent 与
  R3.0-006）。

### 3.6 角色边界与机械/语义分工

| 角色 | 职责 | 禁止 |
| --- | --- | --- |
| 建模 Agent | 理解资料、按切片提出语义候选与证据、发现歧义、申报共享术语与显式未知项 | 拼装平台协议参数 |
| 建模协调 Agent | 维护场景地图（六节合同）、维护切片顺序、跨切片取舍审批、汇总保护 IRI 建议 | 直接调用平台写接口 |
| 平台协议 Agent | 确定性翻译、按序多批次 dry-run/apply、验证/推理/检索、保护集 MCP 调用 | 改变业务语义 |
| Runner/工具 | ID、发布、重试、解析、门的存在性检查、artifact canonical 路径 | 评判语义内容 |

### 3.7 跨切片一致性

由三件事承担：场景地图共享术语注册表（唯一 owner 的机械闭合检查）+ 协调 Agent 取舍审批 +
现有通用平台校验（`run_semantic_validation` / `run_semantic_reasoning`）。**不新建专用一致性
引擎、不做自动术语合并。** 重复/矛盾术语的发现：机械层靠注册表闭合与 owner 唯一性，语义层
靠协调审批与平台通用校验，最终由 R3.0-006 验收。

### 3.8 访谈与输入边界

- 复用现有 interview 流程（MCP：`get_project_brief` / `save_interview_answer` /
  `update_project_brief` / competency questions 工具，加 coordinator 外层用户会话）补齐
  v3 输入包的显式未知项；访谈答案进入场景地图与切片候选的证据。
- **tester-only 业务真值文档绝不进入建模输入**：机制 = v3.0 任务的 `role_sources` 只白名单
  挂载 `modeling-input/` 的 4 个 `allowed_files`（`scenario-brief.md`、`business-terms.md`、
  `schema.sql`、`sample-data.sql`，与 `input-manifest.json` 逐字一致；`input-manifest.json`
  自身不在 `allowed_files` 内，不挂载），Agent namespace 不含父目录（R2.3-001 隔离先例）。
  业务流程参考文档位于输入目录之外，天然不可达。

### 3.9 切片执行顺序

默认**串行** S1 → S2 → S3 → S4 → S5（S5 汇总不新增事实源）；不引入并行执行。流程内调整
切片集合/顺序须在场景地图 `adjustments` 留痕并经协调 Agent 批准；依赖顺序以调整后的场景
地图为准。

## 4. 当前最小范围 vs 未来产品化

- **current minimal scope**：§3.1 表列 8 项增量 + 共享测试计划的确定性/机械验收。
- **future productization（本需求不做，不得进入完成门）**：场景地图平台存储与 UI；拓扑评分
  公式自动化；切片并行与每切片 Agent 编排；中间产物最终 schema；自动术语一致性引擎；
  跨批次事务/回滚；多项目协作；自动重试与长期调度；保护集变更流水线产品化；场景地图版本
  管理与不可变审计。

## 5. 边界与错误行为

1. **拓扑门失败**：fail-closed，独立平台 MCP 门保持关闭。确定性 `reason_code` 集合：
   `topology_missing_artifact` / `topology_unparsable` / `topology_schema_mismatch` /
   `topology_insufficient_options` / `topology_missing_required_option` /
   `topology_missing_dimension` / `topology_empty_dimension` /
   `topology_missing_selection` / `topology_empty_rationale`。失败可自修复：Agent 补齐
   artifact 后重试，run 不终止（T0）。
2. **场景地图结构违约**：`scenario_map.py` 返回确定性错误清单（`map_schema_mismatch` /
   `map_missing_section` / `map_dangling_reference` / `map_term_owner_not_unique` /
   `map_unparsable`）；路径逃逸/符号链接拒绝（先例 `_safe_gate_path`）。
3. **既有任务零行为变化**：无 `multi_slice_workflow` 参数时全部新代码路径不激活（守恒测试）；
   `SAFE_PROTOCOL_TOOLS` 集合字节不变。
4. **多批次失败**：单批次按既有批次失败合同；不新增跨批次错误码。
5. **保护集调用失败**：按 R3.0-004 既有错误合同，不新增错误码或重试策略。

## 6. 发布影响

- 改动全部在 `modeling_team/`（含 `contracts.py`、`runner.py`、`runtimes/codex.py` 增量）；
  backend/frontend 默认零 diff → 无 migration、无服务重启需求。若触发窄修复例外：按 CLAUDE.md
  `cd backend && uv run pytest` 全绿 → `systemctl --user restart ontology-platform.service`
  → 健康检查，并在实现记录中显式论证缺口与修复面。
- 回归：`modeling_team` 全量 pytest（R2.3-009 后基线 970 passed / 1 skipped / 302 subtests
  之上不新增失败）+ ruff；backend 全量 pytest 确认零 diff（当前基线 881 passed / 10 skipped）。
- 对 R2.3-005/R2.3-008/R2.3-009 formal 任务零影响（独立工具集合与任务参数，receipt 管线不动）。

## 7. 验收标准（详见共享测试计划）

| ID | 标准 |
| --- | --- |
| A1 | 配置与合同资产存在且符合：task/profile 加载校验通过、references 合同 JSON schema 自洽、`SAFE_PROTOCOL_TOOLS_R30002` 含 6 个保护集工具且 `SAFE_PROTOCOL_TOOLS` 不变 |
| A2 | 场景地图 artifact 合同：合法 fixture 通过机械校验；违约 fixture（缺节/悬空引用/术语多 owner/非 JSON）确定性拒绝 |
| A3 | 拓扑门行为确定：合格决策记录放行；缺方案/缺规定方案/缺维度/空维度/空理由/缺选择各被拒且 reason_code 确定 |
| A4 | 空/测试作用域机械链路 smoke：场景地图产出 → 拓扑门拦截→放行 → 多批次按序 dry-run 模拟（测试作用域、`dry_run`-only、不 apply）→ 保护 IRI 建议交接物格式校验（+ 测试作用域保护集机械操作与清理） |
| A5 | 守恒与回归：无 `multi_slice_workflow` 参数任务零行为变化；modeling_team/backend 全量回归绿 |
| A6 | 不做真实 modeling start、不消费建模 attempt 预算、不验收语义质量；R3.0-003/005/006 状态不变 |

## 8. 假设（计划评审 Round 1 后更新）

原假设 1（formal candidate gate 开闸点可前置插入拓扑门）与假设 2（三角色 profile 可通过
strict 加载）均被计划评审以代码证据**推翻**（`formal_runs.py:95-101` 封闭注册表、
`runner.py:629-631` 非正式 run 不建门、`runner.py:3424-3454` 开闸点在 acceptance receipt
路径、`contracts.py:413-419` strict 强制四角色）。处置为设计变更而非假设保留：独立平台
MCP 门（§3.1 增量 7、§3.3）与非 formal profile 加载通路（§3.1 增量 6）。剩余假设：

1. **独立门全链路接线正确**：gate 条件谓词统一覆盖 MCP env 传参与沙箱 bind-mount 两处
   （§3.1 增量 7），对既有 formal run 零行为变化——结构上与 formal 路径互斥（同一 run 只
   命中一个条件），但需接线测试断言"两处对 `multi_slice_workflow` 同时为真、对既有任务
   同时为假"（计划评审 High-4：只扩一处会形成沙箱内 state 不可达的死锁）。
2. **确定性 dry-run 批次可脱离 formal 候选通道提交**：计划评审已代码核实**成立**
   （`submit_modeling_batch` 的 dry-run 无候选 receipt 要求，`impact_receipt` 仅约束 delete
   命令；attempt 预算是 modeling_team start-ledger/用户授权层概念，后端批次提交不触发）。
   保留为已验证事实；L2 降级规则（§9.1）作为兜底不变。

## 9. 主代理裁决（2026-08-26，planner 开放决策已全部裁决）

1. **A4/共享测试计划 L1–L4 真实运行轮进入完成门**（测试作用域、disposable Project + 2 个
   测试 Ontology、`dry_run`-only、零 `apply_atomic`、零 RDF 写）：真实平台机械证据优于纯
   单元模拟，且成本有界。降级规则（唯一例外）：若实现时证明 §8 假设 2 的兜底情形发生
   （平台合同要求 formal 候选通道才可提交批次），L2 的批次提交部分降级为单元级模拟，
   L1/L3/L4 照旧，并在测试计划轮次记录中显式记录该平台合同事实与降级证据。
2. **v3.0 真实任务条目现在交付并冻结**（`r3-0-002-multi-slice.yaml`，任务条目内注明
   R3.0-006 用户授权前不得启动）：配置资产完整可评审，git 跟踪防漂移。
3. **接受 prompt 增量落点**：task objective + references 合同为主，共享 `instructions.md`
   只加最少必要段落，减少对 R2.3 已验收共享 prompt 面的扰动。

## 10. 计划评审处置（Round 1，2026-08-26，结论 REVISE → 已回修）

| 发现 | 级别 | 处置 | 依据 |
| --- | --- | --- | --- |
| High-1：formal candidate gate 对未注册 `FORMAL_RUN_CONTRACTS` 的 v3.0 任务不创建、开闸点不可达，原拓扑门接线为空调用 | High | **接受**，改走独立平台 MCP 门（增量 7、§3.3 重写）：门复用 `candidate_platform_gate.py` 机械但由拓扑决策驱动开闸，不注册 formal 合同、不加 acceptance 角色（概要设计 §2.4 三角色边界） | `formal_runs.py:95-101`、`runner.py:629-631`、`runner.py:3424-3454`、`runtimes/codex.py:2757-2791/3641-3652` |
| High-2：strict 加载强制四角色（含 Acceptance），三角色 profile 无法通过 validate/prepare | High | **接受**，保留三角色 roster，增量 6 显式新增非 formal `multi_slice` profile 加载通路（contracts.py 校验分支 + CLI/Runner 加载分派） | `contracts.py:413-419`、`__main__.py:535`、`runner.py:388` |
| High-3："五文件"与 `allowed_files` 实际 4 项矛盾；挂载清单文件违反输入边界 | High | **接受**，role_sources = 4 个 allowed_files，不挂载 `input-manifest.json` | `input-manifest.json` `allowed_files` 恰 4 项，`runtime_boundary` 仅允许点名文件 |
| Low-1：工具名 `list_semantic_protection_set` 与实名不符 | Low | **接受**，§3.5 改为实名 `list_semantic_protection_sets` | `protection_sets.py:30` |
| Low-2：v2 Task 字段集封闭等值校验，`parameters` 键需显式 schema 扩展 | Low | **接受**，并入增量 6 (c) 并要求守恒测试 | `contracts.py` `v2_fields`/`v2_fields_with_binding` |
| Low-3：dry-run 批次须省略 `lease_token` | Low | **接受**，测试计划 L2 注明 | `backend/app/services/modeling_batches.py:260-264` |
| 评审确认的无问题项 | — | 记录：cited 测试文件全部真实；validate CLI 存在；基线 970/1/302 与 881/10 有据；假设 3（dry-run 免 formal 通道、不触发 attempt 预算）代码核实成立；零 backend 改动声明、暂不细化清单、R3.0-003/005/006 边界、L2 降级规则一致性均通过 | 评审报告 |

## 11. 计划评审处置（Round 2，2026-08-26，结论 REVISE → 已回修）

| 发现 | 级别 | 处置 | 依据 |
| --- | --- | --- | --- |
| High-4：gate 接线条件有两个独立来源——MCP env 传参（`codex.py:3641-3652`）与沙箱 bind-mount（`codex.py:3014-3020`/`4024-4036`，派生自 `_is_formal_acceptance_run`）；只扩前者会造成沙箱内 state 文件不可达、后端 MCP 全部平台调用永久 fail-closed，且单元级验收发现不了，顺延 R3.0-006 才暴露 | High | **接受**，增量 7 与 §8/A.1 改写：单一谓词同时覆盖两处，接线测试断言两处对 `multi_slice_workflow` 同时为真、对既有任务同时为假 | `runtimes/codex.py:3014-3020、3641-3652、4024-4036`；`backend/app/mcp/runtime.py:397-420、727` |
| Round 2 核实正确落地 | — | High-1/2/3 与 Low-1/2/3 的 Round 1 处置经复审全部确认（独立门复用既有 state schema 后端零改动、三角色加载分派覆盖本次完成门入口、4 文件白名单一致、工具实名/字段集扩展/lease_token 注明均已落实） | 评审 Round 2 报告 |
| Low-4（Round 2）：closed 门拒绝全部平台调用（含读），设计原文"写调用被约束"措辞差 | Low | **接受**，§3.3 写明 closed 期全拒（循 formal 先例，`runtime.py:477`），防 R3.0-006 误判回归 | `backend/app/mcp/runtime.py:473-493` |
| Low-5（Round 2）：`open()` 强制 7 个候选身份字段，非 formal run 无 receipt 可填 | Low | **接受**，A.1 新增开闸身份字段合成合同（artifact sha256 + run 身份 + 固定 revision，确定性可断言） | `candidate_platform_gate.py:97-148` |
| Low-6（Round 2）：`preview_baseline`/`baseline` 命令仍走 strict，会拒三角色 profile | Low | **接受**，增量 6(b) 注明本次交付不经过该两入口，R3.0-006 真实 run 前补分派（届时完成门项） | `runner.py:1221`、`__main__.py:501` |
| Low-7（Round 2）：§9.1/测试计划 L2 引用"假设 3"已因 §8 重编失效 | Low | **接受**，两处改为"§8 假设 2 的兜底情形" | 文字修订 |

## 附录 A 技术要点（非主线）

### A.1 新文件与接线点

- `modeling_team/scenario_map.py`：纯函数模块，无 I/O 副作用（除显式传入的 Path 读取）；
  `load_scenario_map(path)` / `validate_scenario_map(obj)` / `load_topology_decision(path)` /
  `validate_topology_decision(obj)` / `validate_protection_iri_suggestions(obj)`。
- Runner 接线：`multi_slice_workflow: true`（task `parameters` 新键，contracts.py 校验为
  boolean）→ prepare() 创建独立平台 MCP 门并登记 canonical artifact 路径；开闸前调用
  `validate_topology_decision`，失败保持门关闭并 typed 反馈（不终止 run）；
  `runtimes/codex.py` 的 MCP env 传参与沙箱 bind-mount 两处 gate 条件统一由同一谓词
  （`formal_acceptance or multi_slice_workflow`）控制（见 §3.1 增量 7）。
- **开闸身份字段合成合同**：`CandidatePlatformGate.open()` 强制 7 个非空身份字段
  （`candidate_platform_gate.py:97-148`，含 `original_delivery_id`、`candidate_digest`、
  `semantic_digest`、`candidate_revision` 等）。非 formal 多切片 run 无候选 receipt，身份
  字段全部由确定性 artifact digest 合成，不引入候选 receipt 概念：
  `original_delivery_id = "r30002-topology:{run_id}"`；`candidate_digest` = sha256(
  `topology-decision.json` 字节)；`semantic_digest` = sha256(`scenario-map.json` 字节)；
  `candidate_revision = "1"`；其余必填字段按 `candidate_platform_gate.py` 实名对齐并填充
  run 身份。开闸产物必须在接线测试中被确定性断言。
- 路径检查复用 `_safe_gate_path` 语义（canonical、拒绝逃逸/符号链接）。

### A.2 场景地图字段合同（`r3-0-002-scenario-map/v1`）

| 字段 | 类型 | 机械要求 |
| --- | --- | --- |
| `schema_version` | str | 恰为 `r3-0-002-scenario-map/v1` |
| `scenario_id` | str | 非空 |
| `slices[]` | array | 非空；每项 `slice_id`/`name`/`scope`/`owner`/`status` 非空，`slice_id` 唯一 |
| `shared_terms[]` | array | 每项 `term`、`used_by_slices[]`、`owner_slice`（恰一个，且 ∈ slices）、`notes` 可空 |
| `cross_slice_dependencies[]` | array | 每项 `from_slice`/`to_slice` ∈ slices、`direction` 非空、`connection_points[]` 非空 |
| `cross_slice_competency_questions[]` | array | 每项 `question_id`/`question` 非空、`spans_slices[]` ⊆ slices 且 ≥2 |
| `explicit_unknowns[]` | array | 可为空；每项 `topic`/`needed_from`/`status` 非空 |
| `adjustments[]` | array | 可为空；每项 `change`/`approved_by_coordinator` 非空 |
| `topology_decision_ref` | str | 决策记录产出后非空，指向同目录 `topology-decision.json` |

### A.3 拓扑决策记录（`r3-0-002-topology-decision/v1`）与门检查语义

字段：`schema_version`、`scenario_id`、`options[]`（每项 `option_id`、
`assessment{concept_cohesion, relation_density, reuse, permission_boundary, change_cadence,
cross_domain_query}` 六键值非空）、`selected_option`、`rationale`（非空）、
`decided_by`（非空）。规定 `option_id` 至少含 `single_ontology`、`domain_ontology_split`、
`shared_core_plus_domain`。

门检查（伪码，全部机械）：

```text
exists(path) ∧ parses(path)
∧ schema_version == "r3-0-002-topology-decision/v1"
∧ |options| >= 3
∧ {single_ontology, domain_ontology_split, shared_core_plus_domain} ⊆ option_ids
∧ ∀ option: 六维度键齐 ∧ 每值非空
∧ selected_option ∈ option_ids ∧ rationale 非空
```

### A.4 保护 IRI 建议交接物（`r3-0-002-protection-iri-suggestions/v1`）

字段：`schema_version`、`scenario_id`、`entries[]`（每项 `iri` 为非空绝对 IRI 字符串、
`reason` 非空、`proposing_slice` ∈ slices、`target_protection_set` 为 `existing:<id>` 或
`new:<name>`）、`summarized_by`（非空，协调 Agent）。机械上只校验格式；执行与失败路径归
R3.0-004 既有合同。

### A.5 测试落点

`modeling_team/tests/test_r30002_scenario_map.py`（合同与门）、
`test_r30002_runner_wiring.py`（接线与守恒）、既有 `test_contracts.py`/
`test_runner.py` 扩展用例；fixture 常量只用 `r30002.test` 类命名空间，不进产品代码。
