# v3 执行链缺口收口 — 交付设计附录（2026-09-09）

状态：六项执行链缺口均已实现，独立计划复评与 Round 3 独立机械验收均 **PASS**。
本轮机械交付已完成；R3.0-006 真实语义交付仍为 **PARTIAL / PENDING-AUTHORIZATION**。
本文是已评审 owning designs 的**实现与交付附录**，不是新需求：
它只收口母评审确认的六项执行链缺口（G1–G6），全部复用已通过评审的 006/008B/009/011 设计裁决。
基线 HEAD `6047d38`。权威需求：`docs/requirements/requirements-v3.0.md` R3.0-006/008B/009/011。
Owning designs：`2026-08-27-r3-0-006-real-modeling-e2e-acceptance-design.md`、
`2026-09-03-r3-0-008b-staged-modeling-decision-and-value-acceptance-design.md`、
`2026-09-08-r3-0-009-unified-semantic-graph-design.md`、
`2026-09-08-r3-0-011-competency-question-batch-acceptance-design.md`。
共享测试计划：`docs/delivery/test-plans/2026-09-09-v3-execution-gap-closure-test-plan.md`。

## 1. 目标与非目标

**目标**：让"单条真实 v3 Task 配置 → 分阶段建模 → 统一图物化计划 → CQ 公开投影/冻结 →
真实批次验收 → 外部 Consumer 问数"这条链在授权后的真实 run 中可一次走通；六项缺口的每一项
都是这条链上已证实的断点或未接通的既有能力。本附录只交付机械增量与接线；真实语义取证仍待
R3.0-006 授权（见 §8）。

**非目标**：不改需求边界；不建编排框架/治理/管理 UI；不动 backend/frontend（除非实现中发现
有直接证据的必要缺口，先上报再动）；不启动真实 modeling start、不跑真实 LLM 验收、不做
platform apply；不重写两个既有真实 Task 资产；不做通用适配器/验收器框架；不把机械 PASS
当成语义 PASS。

## 2. 缺口核实结论（全部六项均已按现状代码证实，无一项失效）

| # | 母评审结论 | 核实证据（现状代码） | 结论 |
| --- | --- | --- | --- |
| G1 | 全量真实 Task 缺选择器/引用 | `tasks/r3-0-008b-staged-real.yaml:131-134` 有 `multi_slice_workflow/staged_modeling_decisions/competency_question_acceptance` 无 `unified_semantic_graph`；`tasks/r3-0-009-unified-graph-real.yaml:109-112` 反之，且无 011 合同引用与 CQ 角色；008B objective 仍写 "deferred_contract R3.0-009"（:37）；`agent-packages/modeling/instructions.md:318` 同样固化 `deferred_contract: R3.0-009`，而 `staged_decisions.py:902` 在 unified 模式已要求 `candidate_contract` | 成立 |
| G2 | materialization-plans 写权错配 | `runtimes/codex.py:4153 _staged_decision_binds` 完全不感知 unified：modeling 拿到**整个** `stage3-neutral-graph` 写 bind（含 plans 子目录），protocol 只有 `value-semantics/ledger`；coordinator/protocol 对 candidates/plans 无任何 read bind。009 设计 §3（"新增子目录由 Runner 预建并仅定向赋予 Protocol 写权限，不能依赖原 Modeling-only 的 stage3 bind"）未落地。Runner 侧 `load_materialization_plan_ref`（`staged_decisions.py:2259`）已限定 plans 目录，`staged_decision_directories` 已预建两子目录。**补充（Round 1 H1）**：slot `stage3-neutral-graph/neutral-candidate.json` 目前由 Modeling 经该 bind 直接写（`staged_decisions.py` 只有 load/validate，无 Runner writer；`agent-packages/modeling/instructions.md:318` 即此合同）——把 Modeling 收窄到 `candidates/` 会让 slot 无法发布、run 死锁 | 成立 |
| G3 | 切片公开投影缺失 + 校验未接线 | `runner.py:5247` 仅 panorama-review 分支调 `_write_cq_public_projection`；slice-review 分支只置 `_cq_phase="slice-draft"`（:5249）；`freeze_cq_question_pool`（:5486）不更新投影；`_write_cq_public_projection` 固定 `slice_question_ids: []` 只投影 panorama（`_cq_effective_panorama_questions`）；`verify_cq_scenario_map_projection`（:5447）仅 `tests/test_r3011_runner_wiring.py` 调用；`_handle_staged_submit_modeling_batch`（:3912）不检查 CQ 冻结。读取侧 `_cq_public_projection`（:5427）取最高 ordinal，天然支持追加式投影 | 成立 |
| G4 | 验收命令只产未执行报告 | `__main__.py:463 _run_cq_acceptance` 构建了 platform packet 但把 `sessions` 硬编码 `not-started`、全部 hidden 题记 `unexecuted_question_ids`（:592-611）；`launch_v3_acceptance_child`（`runtimes/codex.py:1699`）仅被 `tests/test_r3011_acceptance.py` 调用；`--model-handoff` 为外部交接输入（011 §4.0），仓库内无 writer（符合设计） | 成立 |
| G5 | Ontology plan 禁止跨 Ontology 共享切片 | `scenario_map.py:319 _validate_ontology_plan`：`assigned.intersection(entry_slices)` → "belongs to more than one Ontology"（:374-378），且尾部要求覆盖消息 "exactly one"（:386）；每 entry `slice_ids` 须非空（:358）。下游 `platform_scope.py:156 apply_ontology_plan` 只做结构校验+确定性串行建 Ontology，**不建 slice→Ontology 索引**，重叠切片集不会破坏它；`runner.py:4253 _apply_multi_slice_ontology_plan` 失败仅记证据不终止 run | 成立（且改动面比预想更窄） |
| G6 | `scripts/r3-0-006/` 不存在 | `ls scripts/r3-0-006` → No such file；`scripts/r3-0-005/{sql_exec_adapter.py,consumer_smoke.py}` 存在且合同冻结（adapter docstring 明确最小边界） | 成立 |

## 3. 最小变更

### G1 — 单条全量真实 Task 入口（新文件 + 两处文案对齐）

1. 新增 `modeling_team/tasks/r3-0-006-real-full.yaml`（`task_id: r3-0-006-real-full`，`schema_version: 2`），
   头部注释写明双重 GATE（R3.0-006 授权 + 009/011 机械增量已交付，沿用 008B/009 资产措辞）：
   - `parameters`: `multi_slice_workflow: true`、`staged_modeling_decisions: true`、
     `unified_semantic_graph: true`、`competency_question_acceptance: true`。
   - `role_sources` = 008B 与 009 真实资产的并集：四个业务输入（scenario-brief/business-terms →
     `[coordinator, modeling, competency-question]`；schema.sql/sample-data.sql →
     `[modeling, competency-question]`，按 008B 先例）；references：`r3-0-002-scenario-map-contract.json`
     与 `r3-0-008b-staged-decisions-contract.json` 与 `r3-0-009-unified-graph-contract.json` →
     `[coordinator, modeling, protocol]`；`platform-neutral-candidate-authoring.json` →
     `[modeling, protocol]`；`modeling-batch-item-contract.json` → `[protocol]`；
     `r3-0-011-competency-question-contract.json` → `[competency-question]`。
   - `expected_terminal_evidence` = 008B 八项 ∪ 009 五项（`stage3-neutral-slot-with-009-contract`、
     `009-candidates-published-with-evidence`、`009-approvals-…`、`009-materialization-plan-with-approved-projection`）
     ∪ `cq-public-projection-published`、`cq-question-pool-frozen-hidden-host-only`。**不**加入
     "真实批次验收 PASS" 类证据：验收命令独立于 run 终态（011 §4.0）。
   - `retain_nonempty`/`semantic_start_evidence` 照抄 008B；`protocol_tools` 照抄（仍省略
     `submit_modeling_batch`）。Profile 固定 `modeling_team/profiles/r3-0-011-competency-question.yaml`。
2. 两个既有 yaml（`r3-0-008b-staged-real.yaml`、`r3-0-009-unified-graph-real.yaml`）**一字不改**，
   作为 legacy opt-in 配置保留，且必须继续通过现有配置加载。
3. 文案对齐（唯一证实的过时点）：`agent-packages/modeling/instructions.md:318` 把
   固化句子改为按挂载合同分派——仅挂 008B 合同时写 `deferred_contract: R3.0-009`，同时挂
   009 合同时写 `candidate_contract: r3-0-009-unified-graph/v1`（取代 deferred）。不改 r2-3 时代
   任务的语义（该句仅在 staged/staged+unified 上下文出现）。`modeling_team/` 内
   `deferred_contract` 其余出现处均为校验逻辑或合同 JSON（行为正确），不改。
4. 若 `contracts.py` 选择器兼容规则拒绝四选择器并集，则在该规则处放行该合法并集（最小 diff），
   并以真实 yaml 加载测试证明（测试计划 T-G1-1/2）；不改其它规则。

### G2 — unified 模式下的写权 bind（Round 1 H1 修订：保留 slot writer，真实拒绝验证）

`modeling_team/runtimes/codex.py`。**slot 归属保持现状**：`neutral-candidate.json` 仍由
Modeling 通过目录 bind 直接发布（不新增 capability、不改路径、不改 008B/009 合同的
"Modeling 写 slot" 语义）。改动是把 modeling 的 plans 子树从可写父 bind 下**读覆盖**出来：

1. Adapter 增加 unified 感知：在为 run 赋 `_staged_decisions_enabled` 的同一处，按 Task
   `parameters.unified_semantic_graph` 赋 `self._unified_graph`（Runner 侧已有同名判定
   `runner.py:3930`，语义一致）。
2. `_staged_decision_binds` unified 模式下的每角色 mount 序列（全部为既有 directory-bind
   机制，依赖 bwrap 顺序挂载"后挂载覆盖先挂载"；仓库内既有先例：value-semantics 只读父 bind
   + 可写子目录覆盖）：
   - **modeling**：`--bind stage3-neutral-graph`（可写整目录，保留 slot 根文件与 `candidates/`
     写入）→ 追加 `--ro-bind stage3-neutral-graph/materialization-plans`（只读覆盖：plans 子树
     在 modeling 命名空间内不可写、不可替换）→ 既有 value-semantics binds 不变；
   - **protocol**：`--ro-bind stage3-neutral-graph`（整目录只读：slot/candidates 计划读可见）→
     追加 `--bind stage3-neutral-graph/materialization-plans`（可写覆盖：仅 Protocol 可发布
     `<plan_id>-r<revision>.json`，与 Runner `plan_ref` 前缀一致）→ 既有 ledger bind 不变；
   - **coordinator**：`--ro-bind stage3-neutral-graph`（整目录只读：slot/candidates/plans 均可
     读，不写）→ 既有 value-semantics/joint-acceptance binds 不变；
   - **competency-question 及其它角色**：无 stage3 bind（011 只读 public 不变）。
   非 unified staged run 返回现有 mount 序列，**字节不变**（F1 承诺保留）。
3. 防绕过依据：modeling 对 plans 的改写/删除/重命名都必须经过被只读覆盖的子树或对挂载点的
   父目录操作；内核对 read-only bind overlay 内写入返回 EROFS，对挂载点 rename/unlink 返回
   EBUSY。**这一点必须用真实 bwrap 文件系统操作证明，不允许只断言参数字符串**（测试计划
   T-G2-1：在真实 bwrap 环境对 slot 写入、candidates 写入、plans 写入、plans 目录 rename/unlink
   四类操作逐一断言实际 errno/结果）。
4. 兜底规则（仅在 T-G2-1 证明 overlay 无法阻止某种变异时启用，属同一最小机制族）：改用
   Runner-host publish —— Modeling 经 Runner 私有 outer 消息提交 verbatim slot/candidate
   JSON，由 Runner 以 host 身份写 `stage3-neutral-graph/`（对齐 intents/receipts 的
   "Runner-host-owned and never bound" 先例），并同步 instructions.md:318 一句话说明该提交
   方式。未触发则不做。
5. 目录缺失沿用 `CodexRuntimeError`（预建于 `staged_decision_directories` unified 分支）；
   Runner 侧 `plan_ref` 限定逻辑不改。

### G3 — 切片公开投影、CQ/生产交付与冻结门（Round 1 修订：真实交付 + 提示条件 + 复用 `_cq_pool_questions`）

`modeling_team/runner.py`（无新框架，全部为既有能力接线）：

1. **投影内容统一由 `_cq_pool_questions()` 派生（不复制决策回放）**：`_cq_pool_questions`
   （`runner.py:5510`）已实现"panorama 决策回放 + 切片决策回放 + 合并 ordering"，本轮不新增
   平行回放 helper。`_write_cq_public_projection` 改为取 `_cq_pool_questions()` 输出、过滤
   `visibility == "public"`，填 `panorama_question_ids`/`slice_question_ids` 与合并
   `ordering`；panorama 阶段输出形状不变（slice 列表为空），既有测试不回归。投影保持追加式
   （`_cq_public_projection` 取最高 ordinal，现状已支持）。
2. 调用点：`_handle_cq_review` slice-review 分支在决策落盘后追加一次投影写入；
   `freeze_cq_question_pool` 在冻结后按冻结快照 public 集合写最终投影（保证"最后一次投影 ==
   冻结公开集"）。hidden 内容永不进入 `competency-questions/public/`；`frozen/`、
   `acceptance-v3/` 保持 host-only。
3. **获批切片 → CQ 的真实交付（现状缺失，无任何既有 seam；Round 2 修订为 map-only seam）**：
   使切片集合"获批"的事件是 Coordinator scenario-map（`scenario-map/scenario-map.json`）
   通过既有 `load_scenario_map` + `validate_scenario_map` 校验，**早于** topology decision、
   中性候选与冻结（requirements-v3.0.md:512-535 顺序）。Runner 在既有 run/drain 轮询路径中
   （每个 drain tick、`_check_multi_slice_topology_gate` 之前）执行一次 map-only 校验
   `_cq_check_scenario_map_slices`：校验通过且切片集合（含 map digest）为新获批变化时，经既有
   `_deliver_to_cq` 直接通道发送 `cq-slices-approved`，载荷为经校验 map 的既有切片字段
   （`slice_id`/`name`/`scope`/`owner`/`status` 的有界切片对象）+ `slice_ids` + map digest +
   run id，不含题干/答案、隐藏内容或整个生产工作区。投递失败时重置指纹并在后续 drain 重试
   （即使 topology gate 已打开）；不新增监视线程，topology gate 的写保护与既有校验不变。
4. **`_task_text` 条件化提示（Round 1 修订）**：现状 schema_version 2 分支对所有角色统一追加
   "read only these role-private sources … call `report_task_result` exactly once before
   ending"（`runner.py:2890-2897`），CQ 与生产角色均无 CQ 输入边界指引。按角色条件追加
   （仅 011 selector 启用时，非 011 run 文本字节不变）：
   - competency-question：获批切片通过 `cq-slices-approved` 直投消息获知；草稿经
     `cq_publish_question_draft` 提交并等待 `cq-review-decision`；不读取生产角色产物、不在
     terminal 消息中携带 hidden 题干/答案；
   - coordinator/modeling/protocol：**能力问题集合**的唯一合法来源是只读 mount
     `/agent/work/competency-questions/public/` 的最高 ordinal `public-projection-*.json`；
     不得把题干/答案原文或投影 dump 复制进平台、Team Transport message 或 candidate 字段，
     不得使用 hidden 内容；获批答案的公开业务语义仍可按常规建模输入建模，但须以投影
     `question_id` 作为 evidence provenance（Round 2 措辞收窄，R3.0-011 公开 Q&A 是显式
     建模输入，requirements-v3.0.md:140）；
   - "report exactly once" 通用句保留不动。
5. `verify_cq_scenario_map_projection` 接线（只降级为可恢复反馈，AGENTS T0）：每次投影写入后、
   若 scenario-map 已存在则调用，不一致时记证据并向 Coordinator 发类型化续跑提示（改地图或
   重新投影任一即可继续），不杀 run；`_handle_cq_handoff_complete` 中强制调用，不一致 →
   现有 `CQContractError` 类型化拒绝（retry 指明对齐方式），可修复后重发。
6. **冻结门前置在中间相位生效，不依赖终态检查**：`_handle_staged_submit_modeling_batch`
   （唯一平台写通道）在 CQ selector 启用且 `self._cq_freeze is None` 时抛
   `StagedSubmissionRejection("cq_freeze_pending", ...)`（可修复、可重试）；即 Modeling 在
   slice 阶段就无法把任何内容物化，冻结顺序由写通道而非终态复核保证。无 011 selector 的
   legacy run 不受影响。
7. 交接条件固定：获批切片 → `cq-slices-approved` → CQ 切片题 → 审核 → 公开投影（首投影在
   panorama 审核、切片投影在切片审核、终投影在冻结）→ 生产角色读取；candidate/batch 发布在
   冻结之后；验收启动以 production delivery ready 为条件（既有 `_cq_production_readiness` +
   `--model-handoff` 合同）。

### G4 — `cq-acceptance` 接通真实 Examiner 与独立 Acceptance（Round 1 H2 修订：sink/proxy v3 分派 + 独立 CLI 生命周期）

`launch_v3_acceptance_child` 只是工厂 seam；真实消费合同在
`modeling_team/acceptance_runtime.py` 的 **`ReportSinkServer`（:2664，经
`_validate_report_sink_payload` 按 kind 校验旧逐题合同）** 与 **`ScopedReadProxy`（:2120，
构造即绑定单 `project_id/ontology_id/graph_set_id`）**，以及
`runtimes/codex.py:2328 _launch_acceptance_child_impl`（kind 枚举、私有根 0700 校验、
child 等待）。三处都仍是旧单题/单 Ontology 合同，v3 必须在**真实 sink/描述符/代理层**做显式
版本分派，而不是只换调用参数：

1. **ScopedReadProxy v3 分派**：新增显式 v3 形态——接受 `authorized_ontologies: list[{project_id,
   ontology_id, graph_set_id, workspace_state/state_digest}]`（packet `model_binding.ontologies`
   同形），保留旧单 Ontology 字段为 legacy 分支；`exact_schemas` 按 v3 只读工具清单校验多
   Ontology scope（禁止按 project 全量扫描的既有约束保持）。旧 packet 构造路径行为不变。
2. **ReportSinkServer v3 分派**：`_validate_report_sink_payload` 增加 v3 batch 报告分支
   （`AcceptanceBatchPacket` schema 判定沿用 `acceptance_branch_for`）：逐题
   `question_id/content_version/answer/evidence/status(completed|unanswered|runtime-incomplete)/
   failure_layer`，绑定 batch_id/freeze_digest/role，拒绝缺题、乱序重题、答案字段缺失；旧
   `source/platform/acceptance` 逐题合同原样保留为 legacy 分支。`kind` 枚举不扩（仍无 Source
   Examiner v3 路径）。
3. **`_launch_acceptance_child_impl` 生命周期**：v3 会话沿用该 impl 的真实私有根/包资产/child
   等待路径（`kind` platform/acceptance 已在枚举内），不改其安全校验；CLI 侧必须**等待 child
   实际完成或超时**后才读 sink 结果（不允许 fire-and-forget），超时产 runtime-incomplete。
4. **独立 CLI 生命周期（不注入工厂也可运行）**：`cq-acceptance` 自身完成
   "读 handoff/冻结 → 组 packet → 启动 ScopedReadProxy（真实 AF_UNIX socket）→ 启动
   ReportSinkServer（真实 socket）→ 调 launcher → 等待 → 收报告 → judge → 落盘 → 清理"
   全链；测试不得通过替换 factory 让流程绕过真实 socket（测试计划 T-G4-1 固定此点）。
   **只读凭据走具体接口**：环境变量 `R3011_ACCEPTANCE_PLATFORM_READ_KEY` 提供平台只读
   API key，交给既有本地 `McpReadForwarder`，由 canonical backend MCP 及其配置访问平台。
   不新增 HTTP forwarder；不提供没有实际作用的 `--platform-base-url`。key 不落盘、不进
   child home/env/receipt；proxy token 由命令进程内生成。缺凭据时以类型化配置错误退出，
   不伪造会话。实际本地配置与调用入口须在交付证据中列明。
5. **pre/post 平台模型状态实读**：启动 Examiner 前、会话结束后，宿主各经同一只读 forwarder
   实读授权 Ontology 的 workspace/graph state，并复用 `model_binding_drift` 比较。实执行路径
   不要求用户在运行前提供未来的 `post_batch_model_binding`；显式未执行报告可保留旧载体合同。
   绑定生产方式须可复用、可说明；漂移或状态读取失败均保留报告并标为未完成，不产 PASS。
6. **Judge 依据包含真实 bytes**：`build_acceptance_judge_packet` 输入含冻结答案要点、Examiner
   reports、以及命令启动时从 run 已挂载获批 role-source 副本/访谈记录组装的**原文副本 +
   locator + 内容 digest + 审核版本绑定**（011 §4.0）；不含 tester-only 真值；Platform
   Examiner packet 永不含依据包/答案。
7. 报告与失败语义：`executed/unexecuted` 按实际会话填充；会话中途不可继续 → 已执行题保留、
   其余 `runtime-incomplete` + `failure layer/reason`，`full_pass=false`，退出码非 0；真实
   错误产"未完成报告"，绝不产伪 PASS。
8. 清理：`/tmp/r3011-acceptance-*` 私有根在 `finally` 删除并记 cleanup；proxy/sink socket
   关闭并在报告记录实际清理结果；不得在清理前预填成功。v3 格式或绑定错误保留可修正反馈，
   不按代码内尝试次数永久拒绝提交，会话总时长由外部 deadline 限定。
9. 保留显式 `--unexecuted-report` 开关（按现行为产"全部未执行"报告，本交付取证用）；默认执行
   真实会话。**实现与提示词不得硬编码 "not authorized"**；授权由用户是否运行该命令决定。
10. 生产 run 零写入：不写 StartLedger、不消费 fresh semantic start、不创建/继续/修复被验收
   run。

### G5 — Ontology plan 允许一个逻辑切片跨多个 Ontology（最小兼容放宽）

`modeling_team/scenario_map.py`：

1. `_validate_ontology_plan`：删除"切片已属其他 Ontology"拒绝分支（:374-378 的 overlap
   检查）；覆盖检查改为 `assigned != set(slice_ids)` → `"every scenario-map slice must be
   covered by at least one planned Ontology"`。保留：≥2 entries、entry 字段集
   `{name, slice_ids}`、name 非空唯一、每 entry `slice_ids` 非空且无重复字符串、dangling
   slice 拒绝（`topology_dangling_slice`）、`single_ontology` 不得带 plan / 其它 selection
   必须带 plan。每个计划 Ontology 仍须至少覆盖一个切片（不发明空 Ontology）。
2. 共享核心+领域拓扑表达：同一逻辑切片的成员可分别落在核心 Ontology 与领域 Ontology，
   无需虚构切片。`PlatformScope.apply_ontology_plan` **不改**（其结构校验本就不含 overlap，
   建Ontology 确定性、串行、幂等不变）；`_apply_multi_slice_ontology_plan` 不改（失败仅记
   证据、不终止 run）。
3. 兼容性：本改动是纯放宽——所有旧合法 plan 仍合法；旧"每切片恰一 Ontology"计划继续通过。
4. 登记修订：`modeling_team/references/r3-0-002-scenario-map-contract.json` 中
   `ontology_plan` 相关"每切片恰一 Ontology"字样改为"每切片至少一个 Ontology，可跨 Ontology
   共享"；本附录 §2/§3.5 即为 R3.0-006/002 的 registered revision 记录，006/002 需求文本的
   对应回填由母流程收口时同步（不阻塞实现）。

### G6 — `scripts/r3-0-006/consumer_rounds.py`（外部化问题 Consumer driver）

1. 新增单文件驱动（平台外部工具，无产品代码），复用 `consumer_smoke.py` 运行形状：
   按轮次 spawn 平台 MCP server（按主体注入 `ONTOLOGY_MCP_API_KEY`）→ 只暴露
   `discover_semantic_scopes/query_semantic_context/get_semantic_read_model` +
   本地 `execute_sql`（shell 到 `scripts/r3-0-005/sql_exec_adapter.py`，**该文件与冻结的
   005 资产一字不改**）→ OpenAI 兼容 tool loop → 全 transcript 落盘（redact key）→ 驱动侧
   判定 PASS/FAIL。
2. 题目与期望**SQL 结果**外部化：`--rounds <path>`（JSON：`question_id`、主体类型、自然语言
   问题、期望答案要点、**期望 SQL 行/列结果 `expected_rows`**、保护断言）。题目文本进入
   Consumer prompt；期望答案与期望行只进驱动侧判定，**不进入 Consumer prompt**；保护上下文来自运行时
   `discover_semantic_scopes` 的动态结果，不写死 fixture/场景名。**SQL 正确性判定 = 对比
   `expected_rows` 与实际 `execute_sql` adapter 行**（按 005 冻结类型合同归一化后比较列/行/
   值）；对自然语言答案的字符串/正则检查只能作附加展示性证据，不得替代行级比较、不得单独
   判 PASS。
3. 环境变量沿用 005 命名（`R3006_SMOKE_LLM_*`、`R3006_SMOKE_KEY_*`；adapter DSN 复用
   `R3005_SQL_ADAPTER_DSN`，因 adapter 自身只读该变量）。`--check` 只如实报告缺失环境
   （健康/adapter/工具面/凭据逐项列出），缺失时以非零退出并注明"未执行"，不得声称已通过
   任何真实 SQL 验收。证据目录 `--evidence-dir`（默认
   `docs/delivery/evidence/2026-09-09-v3-execution-gap-closure/consumer-rounds/`）。
4. 明确边界：本脚本是后续真实 SQL 验收的工具，**不是语义建模启动的前置条件**；不做通用
   adapter 框架、不做数据授权/审计/改写；生产代码（含错误消息）不出现 fixture/客户/场景名。

## 4. 关键影响面（母流程已用最新索引运行 GitNexus impact；planner 复核调用点）

- 已知 helper：`_validate_ontology_plan`（唯一生产调用方 `validate_topology_decision`，下游
  `runner.py:4195/4251/4253` → `platform_scope.apply_ontology_plan` → `protocol_context`）、
  `_staged_decision_binds`（唯一调用方 `namespace_command`）、`_write_cq_public_projection`、
  `_run_cq_acceptance` —— **LOW**。
- `ReportSinkServer` 与 `ScopedReadProxy`（`acceptance_runtime.py`）—— **MEDIUM**
  （各 6 个直接调用方、depth-2 内 14 个符号）：v3 分派必须以新增分支实现，legacy 分支原样
  保留并回归；developer 还须对其实际改动的其它符号（如 `_validate_report_sink_payload`、
  `_task_text`、`freeze_cq_question_pool`）自行运行 impact 并在实现报告中给出结论。
- 无 HIGH/CRITICAL 预期；若 developer 的 impact 返回 HIGH/CRITICAL，须停下上报母流程，
  不得继续编辑该符号。

## 5. 三个关键假设（若不成立需回到母流程）

1. **验收命令默认执行真实会话**，`--unexecuted-report` 仅是显式取证开关；本次交付只用既有
   受控 app-server 子进程 fixture + 真实 proxy/sink socket 测该路径，不跑真实 LLM 验收。
   若母评审要求默认仍为未执行报告，仅需翻转默认值，不影响结构。
2. **新增第三条真实 Task 资产**而非改写两条冻结 yaml；legacy 入口继续可加载（母流程已确认）。
3. **G2 主选方案是"可写父目录 + plans 只读 overlay"（§3.G2.2）**，其安全性由真实 bwrap
   文件系统拒绝测试证明；若测试证明某种变异（如挂载点 rename）未被阻止，则按 §3.G2.4 切换
   Runner-host publish 兜底。G5 已由母流程定为"共享核心列出其服务的原切片，重叠+非空即可"，
   不再是开放假设。

## 6. 错误与可恢复性约定

- 所有新拒绝均为既有类型化通道：`StagedSubmissionRejection`（G3 冻结门）、`CQContractError`
  （handoff 一致性）、`CodexRuntimeError`（bind 目录缺失，run 启动前）、CLI 退出码 + 结构化
  report（G4）。fail-closed 只表示"不写入"，均给出 retry 指引，不杀 run、不产生不可恢复拒绝。
- G3 投影不一致是 author-fixable：Coordinator 可通过更新 scenario-map 或重新审核投影修复，
  同一 run 内继续。

## 7. 完成边界（developer/tester 共同遵守）

1. 变更面 = `modeling_team/**`（tasks/profiles/references/agent-packages/runner/runtimes/
   acceptance_runtime/`__main__`）+ `scripts/r3-0-006/consumer_rounds.py`（新增）+ 本附录与
   测试计划。backend/frontend 零改动；若实现中出现有直接证据的必要缺口，停下上报，不自行
   扩面。既有 dirty `AGENTS.md`、`CLAUDE.md`、`.codex/agents/` 零触碰。
2. 验证要求（按当前实际结果报告，**无任何预设豁免**；任何失败按失败层分类并附证据——
   命令、输出摘要、归因 modeling-quality/platform-contract/collaboration/runtime）：
   - `uv run --project backend python -m pytest modeling_team -q`：**在稳定测试交接点必跑**；
     全绿或逐项分类说明；
   - `cd backend && uv run python -m pytest tests -q`：共享回归**跑一次**；仅当相关变更或
     失败出现时重跑；
   - `uv run --project backend python -m modeling_team validate --profile
     modeling_team/profiles/r3-0-011-competency-question.yaml --task
     modeling_team/tasks/r3-0-006-real-full.yaml`；
   - `uv run --project backend python scripts/r3-0-006/consumer_rounds.py --check`（结果如实
     报告缺失项）；
   - AGENTS 要求的 backend/frontend service restart 仅在相关变更存在时执行并验证端点。
   历史计划中的"7 个环境性失败豁免"与旧通过计数一律不作为本轮依据，以本轮实际输出为准。
3. `detect_changes()`：提交前必跑，核对**实际**受影响符号与执行流（含
   `ReportSinkServer`/`ScopedReadProxy`/`_launch_acceptance_child_impl` 等真实 factory/sink/
   proxy 变更），不要求落在本附录枚举清单内——枚举仅是预期参考，实际 diff 为准。
4. **语义证据边界**：本交付不启动真实 modeling start、不执行真实 L0/L1 批次验收、不做
   platform apply；测试计划中的真实运行用例标记为 PENDING-AUTHORIZATION，仅在用户另行授权后
   由独立轮次取证。这是交付边界陈述，不是代码内硬禁令；fixture 子进程验证结果不得标注为
   真实语义 PASS。
5. 不覆盖/不改写既有设计、测试计划与证据历史；本轮以新文件交付并原地修订。

## 8. Round 1 计划评审记录（2026-09-09，母流程裁定；复评待独立 reviewer，本 planner 不自评 PASS）

| 项 | 发现 | 裁定 | 处置 |
| --- | --- | --- | --- |
| H1 (accepted-high) | G2 初版把 modeling 收窄到 `candidates/`，丢失 `neutral-candidate.json`（slot）写入者，run 死锁；且 mount 测试只断言参数字符串 | 接受 | 本版 §3.G2 重写：保留 modeling 可写父目录 + plans 只读 overlay；新增真实 bwrap 写/读拒绝测试（T-G2-1）与 Runner-host publish 兜底规则（§3.G2.4） |
| H2 (accepted-high) | G4 初版只把 `launch_v3_acceptance_child` 当接线点，未修 `ReportSinkServer`/`ScopedReadProxy`/`_validate_report_sink_payload` 的旧单题/单 Ontology 合同；CLI 生命周期可被注入 factory 替代、无凭据接口 | 接受 | 本版 §3.G4 重写：真实 sink/proxy 层 v3 显式分派 + legacy 分支保留；CLI 全链独立生命周期、`--platform-base-url` + `R3011_ACCEPTANCE_PLATFORM_READ_KEY` 凭据接口、pre/post 实读、T-G4 端到端真实 socket 测试 |
| 母修正 1–7 | 任务资产/G5 口径/G3 交付与提示/G6 行级比较/无预设豁免/影响面更正 | 确认 | 分别落入 §3.G1、§3.G5、§3.G3、§3.G6、§7.2、§4 |

**状态：修订完成，ready-for-re-review**（PASS 与否由独立 reviewer 判定）。

### 8.1 Round 2 实现期母评审修正（2026-09-09，G3 项 7–9；均已落入实现与测试）

| 项 | 发现 | 处置 |
| --- | --- | --- |
| 7 | 初版把 `cq-slices-approved` 交付挂在 `_check_multi_slice_topology_gate` **末尾**（topology decision 校验 + gate.open 之后）；requirements-v3.0.md:512-535 的顺序是 全景审核 → 获批切片 → 切片 CQ/冻结 → 中性候选 → topology，CQ 会等到过晚阶段才收到切片 | §3.G3.3 改为 **map-only seam**：`drain()` 每个 tick 在 `_check_multi_slice_topology_gate` 之前执行 `_cq_check_scenario_map_slices`（仅 `load_scenario_map` + `validate_scenario_map` 校验，无 topology/候选/冻结依赖）；投递失败重置指纹由后续 drain 重试（topology gate 已打开也不阻断）；不新增监视线程，gate 写保护不变。T-G3-3 改为经真实 `drain()` 验证（有效 map + 无 topology decision/无候选/无冻结 → CQ 收到切片） |
| 8 | 初版载荷只有 `slice_ids`/digest/run id，CQ 无法得知每个切片的业务范围 | 载荷改为经校验 map 的既有字段有界切片对象（`slice_id`/`name`/`scope`/`owner`/`status`）+ `slice_ids` + map digest + run id；不引入新语义 schema、不带整个工作区或 hidden 数据。T-G3-3 增加两个切片 scope 互异的交付断言 |
| 9 | `_task_text` 的"不得把投影内容写进平台"过宽，会禁止把获批答案的业务规则作为建模输入（R3.0-011 公开 Q&A 是显式建模输入） | 措辞收窄：禁止复制题干/答案原文或投影 dump、禁止使用 hidden 内容；明确允许按常规建模输入建模获批答案的公开业务语义，并以投影 `question_id` 作为 evidence provenance；"唯一合法来源"限定为能力问题集合，不扩及全部业务证据。仅提示词修正，无新增平台逻辑或门 |

### 8.2 独立计划复评与当前实现裁定（2026-09-09）

独立 plan reviewer 仅复核 H1/H2，结论 PASS：真实 bwrap + 宿主 gate 证明 slot 写入者未丢失；
G4 计划明确 default factory、真实 sink/proxy/MCP、逐题批次报告及独立生命周期。该结论是计划
评审，不是代码或真实语义验收。G2 已在独立机械 Round 1 落实，G4 仍待代码冻结后的 Round 2。

实现期裁定：复用 canonical 本地 McpReadForwarder，删除未交付且未接线的 URL 选项，避免为
该选项增加新的 HTTP 转发路径。v3 报告错误保持可恢复；实际后状态在会话后读取；故障保留
已执行报告；cleanup 只记录实际结果。Judge 材料按源 manifest 及冻结审核绑定核验，允许同一
材料正常挂载给多个角色，并覆盖已保留的访谈记录。这些裁定收窄实现，不增加真实运行授权。

### 8.3 G4 默认子进程复核发现（2026-09-09，实现中）

实际 read_proxy_mcp 会填入首 Ontology 的字段，旧 child 又挂载单题旧 schema 和 Source +
Platform 判定说明；只改变 packet 和 host socket 无法完整接通 v3。收口还包括实际读取桥的
v3 scope/schema 处理，以及挂载 instructions/SKILL 的显式 v3 分派，保留旧 R2.3 提示字节。
新 v3 wrapper 在 destroy 前独立保留已接受报告，并记录该次资源的真实清理结果；模型绑定在
实际 pre-read 后生成，packet/proxy/report/judge 使用同一绑定。测试要求见共享计划补充。

影响证据：`_child_package_assets` pre-edit GitNexus LOW（1 直接调用方、0 已索引执行流）；
`read_proxy_mcp.main` 静态索引未覆盖，impact 返回 UNKNOWN，已人工核对验收与建模两处装载
位置并要求 legacy 回归。此前 `start_roster` 的 HIGH 是 post-edit 补测，已告知用户并留痕，
不将它伪称为 pre-edit 分析；最终提交前另跑全量 changed-flow 核对。

### 8.4 G4 集成期合同修正（2026-09-09，最终测试结果见共享计划）

- 实执行路径将 handoff 作为项目、Ontology 与只读工具授权输入，实际 pre-read 产生本批次状态
  绑定；不要求调用方预计算内部状态摘要，也不要求提供未来 post 状态。逐题 packet、proxy、
  report 与 Judge 使用同一实际绑定；后状态读取失败或发生漂移时保留 Examiner 报告并停止
  Judge 阶段，不能形成 full pass。
- Judge 依据包在权威 builder 处归一化一次，避免将派生 `bundle_digest` 再当作原始输入
  字段验证。Judge 结论沿用 `pass`、`model-recall-insufficient`、
  `question-answer-review`、`platform-runtime-incomplete`，实际 MCP 桥与挂载提示必须一致。
- v3 CLI 保留异常的结构化 reason/evidence 与第一失败层；旧异常字符串格式保持兼容。
  子进程中途退出、Judge setup 或 destroy 异常均不得抹去已接受报告。清理证据来自本次实际
  child、服务线程与 socket 状态，不使用全局目录差集，也不假设所有资源都实现 `active`。
- 三项历史 carrier 测试显式选择 `unexecuted_report=True`，继续验证原来的未执行报告；
  默认执行路径由真实 CLI、受控 App Server、bwrap 和实际 MCP/socket 测试单独证明。
- 集成 fixture 的 MCP 文本确认解析及摘要列表排序问题属于测试工具缺陷；修正测试解析
  不改变产品协议。逐题执行顺序由报告/判定序列验证，`executed_question_ids` 沿用既有
  排序集合摘要。

上述修正不增加业务语义或运行授权。开发者自测、独立机械验证和真实语义验收继续分别记录。

### 8.5 最终机械交付结论（2026-09-09）

全部产品、测试和提示开发由实际 Claude Code CLI 完成；母流程负责设计裁定、交付文档、
验证组织与提交，独立 tester 在最终开发冻结后执行 Round 3。G1–G6 均已机械闭环：
统一真实 Task、分角色物化目录写权、CQ 切片交付与公开投影/冻结、实际批次验收 CLI、
允许共享切片的 Ontology plan，以及外部 Consumer 轮次入口。

Round 2 全量回归发现的 legacy receipt 字段兼容问题，通过独立的 `V3ProxyCallReceipt`
子类修复，保持旧 receipt 的字段集合不变；两个手工构造 fixture 补齐当前构造器已有状态。
v3 acceptance Skill 补齐 YAML 元数据，并对齐获准平台读取与可修正提交的提示合同。
相关四个旧失败用例在 Round 3 全部通过；历史失败证据仍保留。

最终独立结果：全 Team **1405 passed、1 skipped、318 subtests passed**（清除影响
fallback 测试的进程级 `DEEPSEEK_API_KEY`）；G4 与相邻 legacy 聚焦 **143 passed、
11 subtests passed**；实际受控 CLI **7 passed、0 xfail**；Skill validator 通过。
共享后端回归复用本轮 **1006 passed、36 skipped**。详见共享测试计划 Round 3；这些结果
只证明机械与受控子进程合同，不证明真实模型质量、真实 LLM 验收或 SQL 问数质量。

本轮未启动 semantic modeling、真实 L0/L1 验收、platform apply 或真实 SQL Consumer。
backend/frontend 与两条 legacy Task 资产保持基线字节，未触发服务重启条件。
既有 `AGENTS.md`、`CLAUDE.md` 和 `.codex/agents/` 改动保留且不纳入本次提交。

### 8.6 提交前变更范围核对（2026-09-09）

GitNexus 最新代码索引后的 `detect_changes(scope="staged")` 覆盖本次明确暂存的 35 个文件，
风险级别 **HIGH**，列出 9 条受影响执行流；已向用户报告。进一步 `context()` 与暂存 diff
核对表明，5 条通过 CLI `main`，4 条通过 `start_roster`；后者本次仅新增 unified selector
状态赋值。变更符号包括实际 v3 factory、MCP 桥、proxy/sink、CQ 路由、目录 bind 和 Consumer
入口，均落在 G1–G6 及其测试/文档范围内。未发现预期外文件或执行流；机械回归依据为上述
Round 3，HIGH 影响等级不被改写为 LOW，也不替代真实运行证据。

完整输出保留于 `workspaces/modeling-runs/execution-gap-closure-20260909/` 的
`gitnexus-final-staged-detect.json`。暂存 diff 格式检查及 7 份变更 Markdown 的相对链接检查通过。
