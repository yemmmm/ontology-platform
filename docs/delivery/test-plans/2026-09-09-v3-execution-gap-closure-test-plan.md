# v3 执行链缺口收口 — 共享测试计划（2026-09-09）

配套设计：`docs/delivery/designs/2026-09-09-v3-execution-gap-closure-design.md`（下称"设计"）。
基线 HEAD `6047d38`。测试约定：`uv run --project backend python -m pytest modeling_team -q`
（仓库根）；平台回归 `cd backend && uv run python -m pytest tests -q`。无预设豁免：历史计划
中的环境性失败记录与旧通过计数不作为本轮依据，本轮失败一律按实际输出与失败层归因记录。
每轮结果**追加**记录于 §9，不覆盖历史轮次。

最新结果：Round 3 独立机械验收 **PASS**，六项缺口的本轮机械交付完成。
真实语义交付继续 **PARTIAL / PENDING-AUTHORIZATION**，详见文末 Round 3 记录。

边界：本轮只做机械/fixture 验证。所有标记 PENDING-AUTHORIZATION 的真实运行用例（真实
modeling start、真实 LLM 验收、platform apply、真实 SQL 轮次）**不在本轮执行**，待用户
R3.0-006 授权后由独立轮次取证；机械 PASS 不得表述为语义 PASS。

## T-G1 全量真实 Task 入口（真实配置加载 seam）

| 用例 | 做法 | 通过标准 |
| --- | --- | --- |
| T-G1-1 | 经真实配置加载路径（Runner/contracts.py 的 Task+Profile 装载，不是手写 dict）加载 `tasks/r3-0-006-real-full.yaml` + `profiles/r3-0-011-competency-question.yaml` | 加载成功；四选择器全开；`role_sources` 按角色与合同正确 staged；`protocol_tools` 仍无 `submit_modeling_batch`；terminal evidence 含 009 与 CQ 项、不含"验收 PASS"项 |
| T-G1-2 | 同法加载 legacy 两条 `r3-0-008b-staged-real.yaml`、`r3-0-009-unified-graph-real.yaml` | 字节未改、加载成功、原选择器组合不变 |
| T-G1-3 | 断言新任务 objective/挂载合同无 `deferred_contract` 生效路径；`agent-packages/modeling/instructions.md` 在 008B-only 与 008B+009 两种挂载下给出的 slot 字段指引分别匹配 `staged_decisions.py:902` 实际校验 | 文案与校验行为一致 |
| T-G1-4 | CLI：`uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r3-0-011-competency-question.yaml --task modeling_team/tasks/r3-0-006-real-full.yaml` | 退出 0 |

## T-G2 写权 bind（真实 bwrap 文件系统操作 seam，非参数字符串断言）

| 用例 | 做法 | 通过标准 |
| --- | --- | --- |
| T-G2-1 | **真实 bwrap 命名空间内的文件系统操作**：以 unified 配置对 modeling/protocol/coordinator 分别构造并执行 `namespace_command` 产生的 bwrap 命令（或其等价最小 bwrap + 相同 mount 序列的真实进程），在其中以对应角色身份执行操作 | modeling：写 `neutral-candidate.json`（slot）成功、写 `candidates/…` 成功、写 `materialization-plans/…` **失败**（EROFS 类）、对 `materialization-plans` 目录 rename/unlink/chmod **失败**；protocol：写 plans 成功、写 slot/candidates 失败、读 slot/candidates/plans 成功；coordinator：读三者成功、写任一失败。任何一类变异未被拒绝 → 触发设计 §3.G2.4 兜底并复测 |
| T-G2-2 | 同一真实命名空间内断言 mount 序列：modeling 可写父目录 + plans 只读 overlay；protocol 只读父 + plans 可写 overlay；coordinator 只读父；生产角色含 `competency-questions/public` 只读 bind | 序列与设计 §3.G2.2 一致；overlay 位于父 bind 之后（顺序敏感） |
| T-G2-3 | 非 unified staged run（008B legacy 配置）同一构造 | mount 序列与基线字节一致（F1 承诺）；无 009 子目录 bind |
| T-G2-4 | 预建目录缺失场景（移除 plans 目录后构造） | `CodexRuntimeError`，失败发生在 roster 启动前，无半初始化写 |
| T-G2-5 | Runner 侧 `plan_ref` 仍拒绝 plans 目录外路径/符号链接（既有用例回归） | 既有断言全绿 |

## T-G3 投影/冻结门/校验接线（Runner + 真实外层消息 seam）

| 用例 | 做法 | 通过标准 |
| --- | --- | --- |
| T-G3-1 | 经真实 `cq_review` 外层消息完成全景审核后继续切片草稿→切片审核（含 modify/delete/supplement 决策） | 切片决策后追加新的 `public-projection-*.json`：含获批公开切片题/答案、`slice_question_ids` 非空、`ordering` 合并；hidden 题文本/答案**不出现在 public 目录任何文件**；旧投影文件未被改写（追加式） |
| T-G3-2 | 投影内容与 `_cq_pool_questions()` 输出对照（含 modify/supplement/delete 组合） | 投影 == pool 输出过滤 `visibility=="public"`；决策回放只有 `_cq_pool_questions` 一份实现（无平行回放逻辑介入投影） |
| T-G3-3 | Coordinator 批准切片集后（scenario-map 持久化） | CQ 经真实直接通道收到 `cq-slices-approved`（获批切片的 slice_id/name/scope/owner/status + slice_ids/digest）；CQ 据此进入切片题生成；无该消息时 CQ 提示等待而非自行读生产产物 |
| T-G3-4 | 冻结（`cq_freeze` 真实消息）后 | 最终投影 == 冻结快照 public 集合；`frozen/` 与 `acceptance-v3/` 保持 host-only 权限；`evidence/cq-*` 只含 ID/digest |
| T-G3-5 | Coordinator 场景地图 `cross_slice_competency_questions` 与投影故意不一致后触发 `cq_handoff_complete` | 类型化拒绝（含 retry 指引），run 未终止；修复后同一消息重发成功 |
| T-G3-6 | 投影写入时 scenario-map 已存在但暂不一致 | 记录 `cq-projection-consistency` 证据 + Coordinator 收到可修复续跑提示；run 存活 |
| T-G3-7 | CQ selector 启用、未冻结时走 **slice 阶段** staged 提交（首个建模批次前） | `StagedSubmissionRejection("cq_freeze_pending")` 在**中间相位**即拒绝（不依赖终态检查）；冻结后同参提交通过 |
| T-G3-8 | 无 011 selector 的 legacy staged run 提交；及非 011 run 的 `_task_text` | 行为与基线一致（无冻结门、无投影要求）；任务文本与基线字节一致 |
| T-G3-9 | 011 run 的 `_task_text` 分角色断言 | CQ 文本含 `cq-slices-approved`/`cq_publish_question_draft`/`cq-review-decision` 指引与 hidden 不外泄约束；生产角色文本含"唯一合法来源=最高 ordinal public 投影"约束；通用 "report exactly once" 句保留 |
| T-G3-10 | `verify_cq_scenario_map_projection` 在真实 run 流程中被调用（非仅测试直调） | 一致/不一致两分支均有证据记录（真实执行面，不再只是 helper 单测） |

## T-G4 真实验收链路（受控 app-server 子进程 fixture + 真实 proxy/sink socket 端到端，无真实 LLM）

| 用例 | 做法 | 通过标准 |
| --- | --- | --- |
| T-G4-1 | **端到端 CLI**：以既有受控 app-server 子进程 fixture 启动 `cq-acceptance`（默认模式），命令内部真实创建 `ScopedReadProxy`（真实 AF_UNIX socket）与 `ReportSinkServer`（真实 socket），经 `_launch_acceptance_child_impl` 真实 child 路径等待完成；测试**不得**注入假 factory/monkeypatch launcher 来替代该链路 | 两个 v3 会话真实创建（platform examiner + acceptance evaluator）；CLI 等待 child 实际完成；逐题报告落盘 `acceptance-v3/reports/<batch_id>/`；`sessions` 不再是 `not-started`；无 Source Examiner |
| T-G4-2 | **sink v3 合同**：向真实 `ReportSinkServer` 提交 v3 batch 报告（合法/缺题/乱序/缺字段/重复提交/多次修正后提交） | v3 分支按题校验并绑定 batch_id/freeze_digest/role；非法提交得到可操作拒绝，v3 多次格式错误后仍能在会话期限内修正；旧 `source/platform/acceptance` 逐题合同用例**原样全绿**（legacy 分支未回归） |
| T-G4-3 | **proxy v3 合同**：真实 `ScopedReadProxy` socket 上以多 Ontology scope 调用授权只读工具 | v3 `authorized_ontologies` 列表生效（project/ontology/graph_set/state digest 逐项绑定）；越 scope/非只读工具被拒；旧单 Ontology 构造用例原样全绿 |
| T-G4-4 | **凭据接口**：设置/缺失 `R3011_ACCEPTANCE_PLATFORM_READ_KEY`，使用本地 canonical MCP 配置 | 有凭据：既有 McpReadForwarder 用其发起 canonical 平台只读调用；缺凭据：类型化配置错误退出、不伪造会话、凭据不出现在 child home/env/receipt/报告 |
| T-G4-5 | judge 依据包断言 | 含获批材料/访谈 **bytes 副本**、locator、内容 digest、审核版本绑定；Platform Examiner packet 无答案要点、无依据包；Acceptance 无平台写/Team transport |
| T-G4-6 | pre/post 平台模型状态：宿主经同一只读 forwarder 实读 pre/post state 并注入 drift 或 post-read failure | 报告标 runtime-incomplete、证据保留、`full_pass=false`、退出码非 0；不产伪 PASS；生产 run 零写入、StartLedger 无新记录 |
| T-G4-7 | 会话中途 transport 失败/child 超时 | 已执行题保留 + 其余 `runtime-incomplete` + `failure layer/reason`；`/tmp/r3011-acceptance-*` 私有根与 socket 清理且 cleanup 记录入报告 |
| T-G4-8 | `--unexecuted-report` 显式开关 | 输出与基线一致的"全部未执行"报告（本交付取证形态） |
| T-G4-9 | grep 实现与提示词 | 无硬编码 "not authorized"/"未授权" 字样作为行为判定 |

## T-G5 Ontology plan 放宽（真实拓扑→PlatformScope→handoff seam）

| 用例 | 做法 | 通过标准 |
| --- | --- | --- |
| T-G5-1 | 共享核心+领域拓扑：同一 slice 同时出现在核心与领域两个 plan entry，经真实 `validate_topology_decision(slice_ids=…)` 校验 | 0 issue |
| T-G5-2 | dangling slice、缺覆盖切片、单 entry、重名、空/重复 `slice_ids`、`single_ontology` 带 plan | 各自既有/新类型化拒绝保持 |
| T-G5-3 | 旧合法 plan（每切片恰一 Ontology）与既有全部 scenario-map 用例 | 全绿（纯放宽，无回归） |
| T-G5-4 | 放宽 plan 走真实 Runner 路径：拓扑决策 → `PlatformScope.apply_ontology_plan`（scope fixture）→ `protocol_context` 交付 | Ontology 确定性串行创建、幂等复用、ontology-id 集合正确交付 Protocol；失败仅记证据不终止 run |
| T-G5-5 | 保护集建议/PlatformScope 相关既有用例 | 全绿（`apply_ontology_plan` 未改的证据） |
| T-G5-6 | `references/r3-0-002-scenario-map-contract.json` 修订文本与设计 §3.5 一致 | 文档/合同一致检查 |

## T-G6 Consumer driver（CLI/文件 seam，无真实 LLM 轮次）

| 用例 | 做法 | 通过标准 |
| --- | --- | --- |
| T-G6-1 | `uv run --project backend python scripts/r3-0-006/consumer_rounds.py --check`（分别在有/无 DSN、无 LLM key、后端停止三种环境下运行） | 逐项**如实**列出缺失项并以非零退出，明确"未执行"；任何环境下都不得声称已通过真实 SQL 验收 |
| T-G6-2 | 构造 rounds 文件（含 `expected_rows`），断言 prompt 组装与判定分离 | Consumer prompt 只含自然语言问题与运行时动态保护上下文；期望答案、`expected_rows`、评分要点、场景/客户/fixture 名不出现在任何 prompt 字符串与生产代码（grep 证明） |
| T-G6-3 | **行级判定**：驱动侧把 adapter 实际行与 `expected_rows` 归一化比较（相等/行序差异/值类型差异/列缺失各一例） | PASS/FAIL 由行级比较决定；自然语言答案字符串检查不改变判定结果（构造"答案文本正确但行不一致"用例必须 FAIL） |
| T-G6-4 | `execute_sql` 实际 shell 到 `scripts/r3-0-005/sql_exec_adapter.py`（无 DSN 错误路径） | 复用 adapter 合同（input_error/config_error），005 文件内容未变 |
| T-G6-5 | transcript 落盘 | 含问题、工具调用、截断响应、SQL、adapter 输出、期望/实际行对比、最终答案；key 已 redact；默认证据目录正确 |
| T-G6-6 | PENDING-AUTHORIZATION：真实授权后的 SQL 轮次取证 | 本轮不执行，仅登记 |

## 回归与收口

| 项 | 内容 |
| --- | --- |
| R-1 | `uv run --project backend python -m pytest modeling_team -q`：**稳定测试交接点必跑**；报告本轮实际通过/失败数，不引用历史计划的通过计数，也无预设豁免——任何失败逐项附命令、输出摘要与失败层归因（modeling-quality / platform-contract / collaboration-routing / runtime-infrastructure） |
| R-2 | `cd backend && uv run python -m pytest tests -q`：共享回归**跑一次**并报告实际结果；仅当相关变更或失败出现时重跑 |
| R-3 | `detect_changes()`：提交前必跑，核对**实际**受影响符号与执行流（必须覆盖真实变更的 factory/sink/proxy 符号，如 `ReportSinkServer`、`ScopedReadProxy`、`_launch_acceptance_child_impl`）；设计 §3 的符号枚举仅为预期参考，不作为排除必要变更的边界 |
| R-4 | developer 对其新增改动符号（未列入设计 §4 的）自行运行 GitNexus impact 并报告结果；HIGH/CRITICAL 时停下上报 |
| R-5 | 工作区保护：既有 dirty `AGENTS.md`、`CLAUDE.md`、`.codex/agents/` 及他人改动零触碰 |
| R-6 | 清理：测试产生的临时 run root / 假 DSN / fixture 副本按所有者规则删除；证据目录内 transcript 属交付物，保留 |
| R-7 | 无 commit；backend/frontend service restart 仅在相关变更存在时按 AGENTS 执行并验证端点 |

## 完成门

1. T-G1…T-G6 全部非 PENDING 用例 PASS，失败项留痕并修复或经母流程裁定接受；
2. R-1…R-4 全绿/零触碰；
3. 报告明确区分：本交付机械证据 vs 待授权真实语义证据（后者列出：真实 run 取证、真实批次
   L0/L1 验收、真实 SQL Consumer 轮次）；
4. PENDING-AUTHORIZATION 用例在计划中登记而不被静默丢弃。

## 轮次记录（追加，不覆盖）

### Round 1 计划评审（2026-09-09，独立 plan reviewer → 母流程裁定）

- **H1 (accepted-high)**：G2 初版丢失 `neutral-candidate.json`（slot）写入者且 mount 测试仅为
  参数字符串断言。**处置**：设计 §3.G2 重写为"modeling 可写父目录 + plans 只读 overlay"，
  新增 T-G2-1 真实 bwrap 文件系统写/读/改名拒绝测试与 §3.G2.4 兜底规则。
- **H2 (accepted-high)**：G4 初版只接工厂 seam，未修 `ReportSinkServer`/`ScopedReadProxy`/
  `_validate_report_sink_payload` 旧合同，且 CLI 生命周期可被注入 factory 替代。**处置**：
  设计 §3.G4 重写为真实 sink/proxy 层 v3 分派 + legacy 保留；T-G4-1…T-G4-4 改为端到端真实
  socket/凭据/多 Ontology/生命周期测试，禁止假 factory 替代。
- 状态：计划修订完成，**ready-for-re-review**（本轮为计划评审，无测试执行；PASS 由独立
  reviewer 判定）。

| 轮 | 日期 | 执行者 | 范围 | 结果 | 证据 |
| --- | --- | --- | --- | --- | --- |
| （待独立测试轮次追加） | | | | | |
| Round 1 独立组件测试 | 2026-09-09 | independent requirement tester | G1/G2/G3/G5/G6；G4、R-1 与真实授权项待后续 | PARTIAL：冻结组件机械边界通过；G4/全 Team 套件未执行 | workspaces/modeling-runs/execution-gap-closure-20260909/independent-test/round1-component-results.md |
| Round 2 独立 G4 + R-1 | 2026-09-09 | independent requirement tester | G4 四模块/受控 CLI fixture、R-1 全 Team；R-2 复用；真实授权项仍待后续 | **REVISE / FAIL**：G4 聚焦 73 passed；R-1 为 1394 passed、1 skipped、318 subtests、11 failed。D1-D3 为 G4/G3 变更暴露的 legacy/platform/collaboration 回归；D4 为当前 shell credential 污染导致的环境性失败 | workspaces/modeling-runs/execution-gap-closure-20260909/independent-test/round2-g4-full-team-results.md |
| Round 3 独立修复后机械验收 | 2026-09-09 | independent requirement tester | Round 2 四失败 legacy 用例、G4 聚焦与 CLI、skill validator、隔离 credential 的 R-1；R-2 复用；真实授权项仍待后续 | **PASS（机械） / PARTIAL（交付）**：4 legacy PASS；G4 143 passed/11 subtests；CLI 7 passed；validator PASS；R-1 1405 passed、1 skipped、318 subtests、exit 0。真实 semantic/LLM/SQL 仍 PENDING-AUTHORIZATION | workspaces/modeling-runs/execution-gap-closure-20260909/independent-test/round3-final-results.md |

### Round 1 开发者自测记录（2026-09-09，追加；范围=G1/G2/G3/G5 developer 自有机械回归）

执行者：G1/G2/G3/G5 developer（本次交付的开发者自测，**非独立测试轮次**；R-1/R-2 共享全量
回归与独立验收轮次仍归母流程/独立 tester，本记录只登记开发者聚焦命令与实际退出码）。
基线 `6047d381`。无真实 modeling start、无真实 LLM 验收、无 platform apply、无真实 SQL 轮次。

| 用例/命令 | 结果 | 证据 |
| --- | --- | --- |
| T-G1-1…T-G1-4（`modeling_team/tests/test_r3006_real_full_task.py` + T-G1-4 validate 命令另测） | 见下行命令；legacy 两条任务以冻结 SHA256 常量断言字节不变（一次性基线 diff 作为交付证据保存在 developer-progress.md，持久测试不再依赖 Git 对象） | `logs/`（workroot） |
| T-G2-1…T-G2-5（`modeling_team/tests/test_r3006_unified_binds.py`，含 H1：modeling 命名空间经真实 bwrap 写入 009 合法 slot+candidate bytes → 宿主 `validate_stage3_slot(unified=True)`/`validate_unified_candidate`/`staged_stage3_issue` 接受同一文件） | **9 passed**（exit 0） | 同上 |
| T-G3-1…T-G3-10（新增 `modeling_team/tests/test_r3011_g3_cq_routing.py`；T-G3-3 经真实 `runner.drain()`：有效 scenario-map + 无 topology decision/无候选/无冻结 → CQ 经直接通道收到含 5 个有界切片对象的 `cq-slices-approved`，gate 保持 closed，失败投递在后续 drain 重试） | **11 passed**（exit 0） | `logs/g3-routing.log` |
| 聚焦回归：`test_r3011_runner_wiring.py` + `test_r3011_cq_lifecycle.py` + `test_r30002_runner_wiring.py` + `test_r30002_scenario_map.py` + `test_r3006_real_full_task.py` + `test_r3006_unified_binds.py` + `test_r30006_mechanical_increments.py` + `test_r30009_runner_wiring.py` + `test_r30009_unified_graph.py` + `test_r30008b_runner_wiring.py` + `test_r30008b_staged_decisions.py` + `test_codex_isolation.py` | **295 passed, 64 subtests passed**（exit 0） | `logs/g3-regression.log` |
| T-G5-1…T-G5-3/T-G5-6（含于 `test_r30002_scenario_map.py` + `test_r30006_mechanical_increments.py`） | 全绿（含于上一行计数） | 同上 |
| R-3 `detect_changes()` | 提交前由 developer 执行（本轮无 commit）；结果见 workroot `developer-progress.md` | 同上 |

范围与归属说明：
- **G6 已由第二 developer 冻结为 DEVELOPMENT-READY**：T-G6-1…T-G6-5 机械回归 **29 passed**
  （T-G6-6 PENDING-AUTHORIZATION），详见 workroot `consumer-developer-result.md`，非本记录范围。
- **G4 由第三 developer 负责**（`acceptance_runtime.py`/`__main__.py`/`report_sink_mcp.py`/
  codex.py G4 方法/`test_r3011_acceptance.py`），冻结后经 `acceptance-developer-result.md`
  报告；T-G4 用例结果由其登记，本记录不含、也不视为缺口。
- PENDING-AUTHORIZATION 项（真实 run 取证、真实 L0/L1 批次验收、真实 SQL Consumer 轮次、
  T-G6-6）本轮一律未执行；机械 PASS 不表述为语义 PASS。

### Round 1 独立组件测试记录（2026-09-09，G1/G2/G3/G5/G6；G4 与全 Team 套件待后续）

执行者：独立 requirement tester。基线 6047d38112b9b1a34440c48faa9e2dca406afd1。
本轮严格沿用本计划 T-G1/T-G2/T-G3/T-G5/T-G6，未修改产品代码、仓库测试或 G4 文件；
未启动真实 semantic modeling、LLM、platform apply、SQL 验收或平台写入。环境为
Python 3.11.15、uv 0.11.3、bubblewrap 0.9.0。

| 用例/命令 | 独立实际结果 | 证据 |
| --- | --- | --- |
| T-G1-1…T-G1-3：uv run --project backend python -m pytest modeling_team/tests/test_r3006_real_full_task.py -q | **PASS**；4 passed，exit 0 | workspaces/modeling-runs/execution-gap-closure-20260909/independent-test/round1-component-results.md |
| T-G1-4：uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r3-0-011-competency-question.yaml --task modeling_team/tasks/r3-0-006-real-full.yaml | **PASS**；exit 0，四角色 roster 输出正确 | 同上 |
| G1 legacy 字节保持：git diff --quiet 6047d381... -- modeling_team/tasks/r3-0-008b-staged-real.yaml modeling_team/tasks/r3-0-009-unified-graph-real.yaml | **PASS**；exit 0，无差异 | 同上 |
| T-G2-1…T-G2-5：uv run --project backend python -m pytest modeling_team/tests/test_r3006_unified_binds.py -q | **PASS**；5 passed，exit 0。T-G2-1 实际运行 bwrap 文件系统操作并验证 slot/candidates/plans 的角色写权、plans 目录 rename/unlink/chmod 拒绝，以及宿主 gate 接受相同字节 | 同上 |
| T-G3-1…T-G3-10：uv run --project backend python -m pytest modeling_team/tests/test_r3011_g3_cq_routing.py -q | **PASS**；11 passed，exit 0 | 同上 |
| G3 相邻回归：test_r3011_runner_wiring.py、test_r3011_cq_lifecycle.py、test_r30002_runner_wiring.py、test_r30009_runner_wiring.py、test_r30008b_runner_wiring.py | **PASS**；101 passed，exit 0 | 同上 |
| T-G5-1…T-G5-5：uv run --project backend python -m pytest modeling_team/tests/test_r30002_scenario_map.py modeling_team/tests/test_r30006_mechanical_increments.py -q | **PASS**；75 passed、16 subtests passed，exit 0 | 同上 |
| T-G5-6：JSON、git diff --check 与合同文案检查 | **PASS**；合同允许共享 slice 由多个 Ontology 服务，同时保留至少一个覆盖、dangling、非空/唯一约束 | 同上 |
| T-G6-2…T-G6-5：uv run --project backend python -m pytest modeling_team/tests/test_r3006_consumer_rounds.py -q | **PASS**；29 passed，exit 0 | 同上 |
| T-G6-1/T-G6-4：consumer_rounds.py --help、无 DSN/后端停止或健康、不可达 DSN 的 --check，以及冻结 SQL adapter 的 config/input 错误路径 | **PASS**；help exit 0；所有未就绪/adapter 错误 exit 1，均明确未执行 Consumer/真实 SQL 验收，未伪造 PASS | 同上 |
| R-2 共享后端回归 | **REUSED**；主流程既有 1006 passed, 36 skipped, 413 warnings, exit 0，本轮未重复运行 | workspaces/modeling-runs/execution-gap-closure-20260909/backend-regression-result.md、backend-regression.log |

失败归因/第一阻塞层：本轮 G1/G2/G3/G5/G6 未出现失败，因此没有新增
modeling-quality、platform-contract、collaboration-routing 或 runtime-infrastructure
缺陷。配置缺失和不可达 DSN 是 T-G6 设计中的受控、可操作的 BLOCKED/非零检查结果，
不是产品缺陷。未执行项的阻塞层是范围/授权：G4 尚未冻结，真实语义、LLM、SQL 和 platform
apply 仍 PENDING-AUTHORIZATION。

证据记录备注：workroot/developer-progress.md 早先将 test_r3006_unified_binds.py 记为
9 passed；本轮同一当前工作区文件独立复测实际为 5 passed，且当前文件收集到 5 个测试函数，
T-G2-1 在单测试内包含多项真实 bwrap 操作。该低严重度测试记录计数差异不构成 G2 功能缺陷；
收口应以可复现的独立 5 passed 与实际 bwrap 输出为准，或补充旧计数来源。

**本轮总体结论：PARTIAL。** 冻结组件 G1/G2/G3/G5/G6 的独立机械边界通过；不能形成整体
PASS，因为 G4 和 uv run --project backend python -m pytest modeling_team -q 全 Team 套件
尚未按任务书执行。G4 冻结后，下一轮复用本计划，优先执行 G4 失败/阻塞用例，再运行全 Team
套件并更新最终独立结论。真实 R3.0-006 L0/L1/SQL 证据仍不由本轮机械结果替代。

### 母流程记录更正与 G4 实现裁定（2026-09-09）

- 独立计划复评 H1/H2 已 PASS；该结果不替代实现测试。
- 开发记录中 G2 的 9 passed 是 G1（4）与 G2（5）合并命令的总数；独立 Round 1 的 G2 单项
  5 passed 正确。保留原历史记录，本条澄清计数来源。
- G4 复用本地 canonical McpReadForwarder，移除新增但无实际作用的 URL 选项；T-G4-4 验证
  实际只读 key/config/forwarding 路径。无新 HTTP 转发框架。
- Round 2 须覆盖：正常多角色源副本、源 hash 不匹配、访谈依据；v3 多次格式错误后的有效
  提交；post-read/Judge setup 失败仍保留已执行报告；清理真实结果与失败；实执行路径不依赖
  预先伪造的未来 post binding。仍通过既有 T-G4 用例组织，不增加真实 LLM/SQL 运行。

### G4 实际子进程合同补充（2026-09-09，母流程复核发现）

T-G4-1/T-G4-3 必须经过真实 read_proxy_mcp 与 report_sink_mcp：测试第二个 Ontology 的单独
读取，以及授权 A/B/C 时只选择 B+C 的读取；宿主按获准选择确定每项状态，不能被旧桥的首项
提示字段误导。真实桥接应向子进程公开当前 v3 schema，legacy 模式继续兼容。

T-G4-1 还必须检查实际挂载的 instructions 与 SKILL 内容。旧单题 payload、Source + Platform
双报告以及旧推理次数限制不得作为 v3 批次提示输入。仅让受控子进程无视旧提示并输出合法 v3
报告，不能证明这一提示合同已接通。旧 R2.3 提示文件保持原样。

T-G4-7 的部分报告检查须跨过真正的 destroy：旧 child 清理会清空共享报告列表，新 v3 边界
必须在清理后仍保留已接受的题目结果。cleanup 按该次实际 child/forwarder 结果记录，不能用
全局临时目录差集推定资源归属；其他批次目录不影响该次结果。

### Round 2 独立 G4 + R-1 测试记录（2026-09-09）

执行者：独立 requirement tester。G4 两位开发者已声明冻结后，按本计划执行四个 G4 测试模块与一次 R-1；本轮未修改产品代码、仓库测试、G4 fixture 或测试方案，未启动真实 semantic modeling、LLM、platform apply、SQL 验收或服务重启。

| 范围 | 实际结果 | 证据 |
| --- | --- | --- |
| G4 聚焦：`test_r3011_acceptance.py`、`test_r3011_acceptance_runtime.py`、`test_r3011_acceptance_cli.py`、`test_r3011_acceptance_cli_flow.py` | **PASS**；73 passed，exit 0，7.01s | `workspaces/modeling-runs/execution-gap-closure-20260909/independent-test/round2-g4-full-team-results.md` |
| T-G4-1 真实受控 CLI fixture | **PASS**；CLI flow 7 tests collected/执行，0 xfail；实际默认 acceptance factory、受控 App Server 子进程、真实 AF_UNIX proxy/sink/canonical forwarder、实际 mounted prompt/skill、multi-Ontology 与失败保留路径均通过 | 同上；fixture source 与 collect-only 输出保留在 Round 2 记录 |
| R-1：`uv run --project backend python -m pytest modeling_team -q` | **FAIL**；1394 passed、1 skipped、318 subtests passed、11 failed，exit 1，60.24s。产品相关失败 4 个：D1 两个 legacy `ScopedReadProxy` page 用例，D2 一个 legacy receipt exact-set 用例，D3 一个 legacy hand-built `TeamRunner` drain 用例；其余 7 个是当前 `DEEPSEEK_API_KEY` 已设置导致 fallback 测试未进入临时 `.env` 分支 | `round2-g4-full-team-results.md`、`round2-legacy-failures.log` |
| bounded baseline | 临时 detached `HEAD=6047d38` worktree 重跑上述 4 个 legacy 用例 | **PASS**；4 passed，0.50s，确认 D1-D3 是当前变更回归而非基线既有失败 | `round2-baseline-legacy.log` |
| D4 环境归因复核 | 清除 `DEEPSEEK_API_KEY` 后相同 7 个参数化案例 7 passed；不把原始 R-1 的 7 个失败静默抹除 | `round2-deepseek-env-unset.log` |
| R-2 | **REUSED**；1006 passed、36 skipped、413 warnings、exit 0 | `backend-regression-result.md`、`backend-regression.log` |

独立结论：**REVISE / FAIL（R-1 机械回归未通过）**。G4 新增受控端到端链路本身 73/73 通过，但 D1-D3 是本次 G4/G3 变更暴露的 legacy/platform/collaboration 回归，应由需求开发 agent 修复后复测相同窄用例并重跑 R-1。D4 属于测试环境 credential 污染，需在无该变量的可复现环境复核；它不是 G4 产品缺陷。真实 semantic modeling、真实 L0/L1 acceptance、platform apply 与真实 SQL Consumer 轮次仍为 PENDING-AUTHORIZATION，因此交付总体继续标记为 **PARTIAL**，机械回归不能替代真实语义证据。

缺陷摘要：

- **D1 / High / platform-contract**：`acceptance_runtime.py:2576` 的 v3 分支直接访问未由旧 `object.__new__` fixture 初始化的 `authorized_ontologies`，两个 legacy receipt/page 用例抛 `AttributeError`。
- **D2 / High / platform-contract**：`ProxyCallReceipt` 新增 `ontologies` 字段后，`acceptance.py:4704` 的 legacy exact-set 校验拒绝空 tuple 也合法的旧 receipt，C49 settlement 失败。
- **D3 / High / collaboration/routing**：`runner.py:6948` 无条件调用新 CQ drain hook，`runner.py:5138` 读取旧 hand-built runner 未设置的 `_competency_questions`，issue escalation 用例失败。
- **D4 / environment / runtime-infrastructure**：当前 shell 的 `DEEPSEEK_API_KEY` 使 `_resolve_deepseek_api_key` 优先使用 process key；清除变量后 7 个 fallback 用例通过。原始 R-1 失败仍保留为实际结果。

本轮建议父流程让需求开发 agent 关闭 D1-D3 后，再复测上述失败用例与 R-1；没有建议把环境性失败改写成 PASS，也没有发起真实授权运行。

### Round 3 独立修复后机械验收记录（2026-09-09）

执行者：独立 requirement tester。Round 2 的 D1-D3 修复及 v3 acceptance skill 修复已重新冻结后，按本计划优先复测四个旧失败用例，再执行 G4 聚焦、实际 CLI flow、skill validator 和指定隔离 credential 的 R-1。没有修改产品代码、仓库测试或 fixture；没有启动真实 semantic modeling、LLM、platform apply、SQL 验收、服务重启或提交。

| 范围 | 实际结果 | 证据 |
| --- | --- | --- |
| Round 2 四个 legacy 失败用例 | **PASS**；4 passed，0.20s，exit 0 | `workspaces/modeling-runs/execution-gap-closure-20260909/independent-test/round3-final-results.md` |
| G4 + 相关 legacy 聚焦 | **PASS**；143 passed、11 subtests passed，3.14s，exit 0 | 同上 |
| G4 真实受控 CLI flow | **PASS**；7 passed，4.85s，exit 0，0 xfail；默认 factory、受控 App Server、真实 AF_UNIX proxy/sink/MCP、mounted prompt/skill 与失败保留路径保持通过 | 同上 |
| v3 acceptance skill validator | **PASS**；`Skill is valid!`，exit 0 | 同上 |
| R-1：`env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q` | **PASS**；1405 passed、1 skipped、318 subtests passed，58.59s，exit 0 | `independent-test/round3-full-team.log` |
| R-2 | **REUSED**；1006 passed、36 skipped、413 warnings，exit 0 | `backend-regression-result.md`、`backend-regression.log` |

独立 Round 3 结论：**PASS（机械验收）**。Round 2 的 D1-D3 已通过修复后窄测，G4 聚焦与实际 CLI flow 通过，skill validator 通过，隔离 credential 下 R-1 全 Team 通过；本轮没有新增缺陷或未执行的必测项。交付层面仍为 **PARTIAL**，因为真实 R3.0-006 semantic modeling、L0/L1 batch acceptance、platform apply 与真实 SQL Consumer 轮次仍为 PENDING-AUTHORIZATION，机械 PASS 不替代这些运行时/语义证据。本轮按任务要求停止。

### 母流程提交前收口记录（2026-09-09）

- R-3：最新代码索引后对本次 35 个暂存文件执行 GitNexus `detect_changes`，结果 HIGH、
  9 条受影响执行流；已报告并按 CLI `main` 与 `start_roster` 两个入口复核，均属 G1–G6
  预期范围。详见设计 §8.6 与 workroot `gitnexus-final-staged-detect.json`。
- `git diff --check`、暂存差异检查及 7 份变更 Markdown 的相对链接检查通过。
- 原有用户改动保持；backend/frontend、冻结的旧任务与 SQL adapter 无差异，无服务重启。
- 本轮机械交付完成。真实 semantic modeling、L0/L1、platform apply、SQL Consumer
  仍 PENDING-AUTHORIZATION，未消耗真实 semantic start 额度。
