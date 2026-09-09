# R3.0-011 能力问题驱动建模与批次级语义验收 — 共享测试计划

- 关联设计：[2026-09-08-r3-0-011-competency-question-batch-acceptance-design.md](../designs/2026-09-08-r3-0-011-competency-question-batch-acceptance-design.md)。
- 当前状态：计划评审 Round 3 两项 High 修订后送 Round 4 专项复审（Round 1/2 记录保留）；功能测试 Round 1 已执行（2026-09-09：机械/隔离 REVISE）；复测 Round 2 已执行（F1–F6 FIXED，新 F7 High → 仍 REVISE）；复测 Round 3 已执行（2026-09-09，仅变更面：F7 FIXED、R4 非盲测标注 FIXED、`pass`+layer 守卫闭合 → **机械/隔离 PASS**；L0/L1 BLOCKED，未启动真实 modeling start，无语义质量结论）。本轮不启动真实 modeling start，也不把 fixture/机械 PASS 当成语义质量 PASS。
- 权威边界：`requirements-v3.0.md` R3.0-011 D1–D10；真实 SQL/RDF/Project authorization 继续引用 R3.0-006/008B/008A，009 的共性抽象只验其自身合同。

## 1. 测试分层和固定规则

测试分成文档/合同核对、机械与隔离、L0 Runtime、L1 Modeling quality、L2 Repeatability、L3 Productization。后一层不是前一层的前置；机械检查不能替代独立语义验收，语义 Acceptance 不能创建/继续/修复被验收生产 run。

每个用例记录：代码/文档 revision、profile/task、run/batch/session ID、role source manifest、artifact digest、授权 scope、执行/未执行题清单、状态、failure layer、cleanup owner 和证据路径。所有失败保留原始证据和修复轮次。

推荐命令（实现阶段按实际新增测试文件调整）：

```bash
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-011-competency-question.yaml \
  --task modeling_team/tasks/r3-0-008b-staged-real.yaml
uv run --project backend pytest -q modeling_team/tests/test_r3011_*.py
uv run --project backend pytest -q modeling_team/tests/test_r30002_runner_wiring.py modeling_team/tests/test_r30008b_*.py
cd backend && uv run pytest
```

真实运行仍须按仓库授权流程、`r3-0-008b-staged-real.yaml` 双重门和 R3.0-006 用户授权执行；没有授权时只能做 L0 预检/机械 smoke，不能调用真实任务的 `run` 命令启动 semantic start。

## 2. 文档和合同核对（D）

| ID | 检查 | 通过证据 |
| --- | --- | --- |
| DC1 | 需求、设计、计划互相引用；D1–D10、非目标、四态、四层归因、D5 延后 model binding 均写明 | `rg`/链接检查，人工逐项核对；无实现/运行完成措辞 |
| DC2 | 008B stage 2 在切片前接收 CQ public projection；009/008A/006 交界不重复建设 | 需求与关联设计段落/路径核对 |
| DC3 | 旧 R2.3 Source/Platform/Acceptance fresh 合同与新 v3 batch 合同分开 | 旧 profile/task/schema 快照与新 selector 对照 |
| DC4 | 建议题量是建议而非硬门，用户审核不能由 Agent 推荐替代 | 合同字段和负例检查 |

## 3. 机械合同、选择器和成功边界（M）

| ID | 场景 | 预期 |
| --- | --- | --- |
| M1 | 011 参数为 true，加载 011 Profile + 008B staged real task | loader 接受：核心三角色各一、CQ role 各一、profile/task digest 一致；不启动 Agent |
| M2 | 旧 002 Profile/Task、旧 R2.3 formal Profile/Task 不带 011 参数 | 行为、role set、capability 广告和旧 schema 回归；不出现 CQ operation |
| M3 | role/package 合同、`ROLE_VALUES`、Profile extra role、task parameter 及通信边 | 缺 role/重复 role/未知 parameter/缺核心角色/非法边 typed reject；额外 CQ 不被“固定三角色”误拒 |
| M4 | role source manifest | CQ 与 Modeling 获得同一四个业务输入；生产角色未获得 tester-only、参考答案、CQ private；Acceptance 只获得冻结的引用原文副本；Examiner 未获得 source directory 或原文 |
| M5 | `cq_publish_question_draft` 工具广告和 dispatch | 仅 011 CQ endpoint 广告；schema、owner、run ID、content digest、revision 错误只拒当前草稿；CQ 无 platform tool，生产角色无 CQ private tool |
| M6 | public projection | 全景审核后只将获批 public 题/答案投影给切片生产角色；投影不含 hidden 题干、答案、ID 提示、CQ 私聊或未审核记录；scenario map 的 `cross_slice_competency_questions` 节只含公开投影题（ID/题干一致）或显式置空且记录覆盖缺口，Coordinator 从原始材料新撰的跨切片题干被拒绝或要求回退 |
| M7 | review action | `cq_interview`/`cq_review` 仅接受 outer FIFO 的严格字段，直接唤醒 CQ；批量/逐题批准、修改、删除、补题皆可；revision/digest/owner 错误经CQ专用分支拒绝，不经 Coordinator；验证CLI/FIFO仍存活、run/session ID不变、下一条合法审核成功，旧receive_outer致命边界不被广泛吞掉 |
| M8 | 分组时点 | 全景 hidden 预留、slice 只读 public projection、slice 审核后最终 freeze；曾展示给任一生产角色的题在负例中不能转 hidden |
| M9 | freeze snapshot | 稳定题 ID、scope、题干、答案要点、依据、unknown、visibility、review version/binding、材料 digest、snapshot digest 闭合；旧版本追加保留，不能原地覆盖 |
| M10 | 题量边界 | 低于/高于建议范围、切片数量变化、重复候选只给可修复反馈或按用户批准继续；不因固定题数、切片数、Agent 数硬拒 |
| M11 | D5 late model binding | 冻结阶段没有虚构 workspace/model state；验收启动时绑定每个显式 Ontology 的授权和状态，缺状态/越权/漂移拒 batch；不全项目扫 |
| M12 | 独立验收启动/终态 | `cq-acceptance` 读取原 run 配置，绑定freeze和稳定交付模型；pending checklist不阻止启动，生产未静默/未决写入不能开始；Evaluator输出host-only报告，Delivery只交脱敏摘要，不产生终态循环；`cq-acceptance` 全程只读，不写 StartLedger、不消耗 fresh semantic start 授权额度；CQ跨全景/切片审核复用同session，frozen不提前终态，production handoff后接收cq_handoff_complete并恰好一次report_task_result；全roster可settle，不等Acceptance才结束CQ；提前terminal只拒当前调用，不入账且同session可继续 |
| M13 | v3 packet与角色提示 | Platform为单批次session、无Source；随后独立Acceptance session只读冻结输入并交报告；实际工具广告和提示匹配v3，不要求旧source report，不允许Acceptance启动/继续/修复run |
| M14 | 参考答案依据 | Acceptance收到冻结引用原文/访谈bytes与digest，能识别原文与答案冲突；Examiner看不到该包；纯待复核允许failure_layer为空，不能误算modeling-quality |
| M15 | 验收期间模型变化 | 前后状态重验发现变化时不沿用旧PASS，保留旧batch并标未完成；不新增锁/状态管理框架 |
| M16 | 空隐藏集/切片无有效隐藏题 | 可以继续建模，但保留验收覆盖缺口；不以空集合或删题后的分母产生整批/全场景PASS |

## 4. 信息隔离和泄漏负例（I）

| ID | 检查面 | 预期失败/证据 |
| --- | --- | --- |
| I1 | `role_sources` | Modeling/Coordinator/Protocol 尝试读取 CQ private、hidden freeze、参考答案或 tester-only 路径均不可读；CQ 可继续读获准业务材料 |
| I2 | artifact bind | 生产角色 namespace 只挂 public projection；CQ private/reviews 和 hidden packet 不存在于其路径；Examiner 不见 answer/frozen reference，Acceptance 不见生产私聊 |
| I3 | team messages/log/history | hidden question/answer/答案提示/未过滤 review 文本不得进入 Coordinator/Modeling/Protocol delivery、team transport event log、role history、共享 evidence 文本、scenario map 等生产 artifact 文本；只保留 IDs/digest/status/path |
| I4 | capability endpoint | 011 selector 广告和 role-token 绑定准确；CQ 不能调用 platform/read proxy，Modeling 不能请求 hidden packet，Examiner 只能只读语义 + report sink，Acceptance 不能写平台或启动 Agent |
| I5 | repeated exposure | 模拟先 public 后改 hidden、CQ 向 Coordinator 误发 hidden、共享目录放置 hidden 文件；Runner 保留泄漏证据、把题永久 public 或 reject，不能继续把它计 blind |
| I6 | authorized multi-Ontology | hidden packet 只含获准 Ontology 显式列表；未授权 Ontology、跨 project IRI 和不存在/无权语义都不通过错误侧信道泄漏 |

## 5. 审核、恢复和报告机械用例（R）

| ID | 场景 | 预期 |
| --- | --- | --- |
| R1 | 审核等待/暂停、用户补题或修改一题 | run 可恢复；只重做受影响 panorama/slice 阶段，不消耗 semantic start，不重置其他批准；暂停审核不触发CQ任务失败/cleanup，恢复后同CQ session继续；等待时长超过 `run_fallback_timeout_seconds`（默认 5400 秒）后 run 仍可恢复，审核/handoff 等待窗口不计入 active 超时，不触发 `run-fallback-timeout` terminal latch，T3 对无等待真实停滞的保护不回退 |
| R2 | 题目/答案与材料冲突、未知项缺依据、重复/过期 revision | `question-answer-review`/typed contract error；原题、冲突依据、coverage gap 保留，不静默删除或 PASS |
| R3 | 冻结后用户修题 | 新 content version/review binding；旧题、旧答案、旧报告和裁决只读保留，后续新 batch 明确影响 |
| R4 | hidden 内容泄漏给生产角色后修模 | 受影响题转 public；可以继续生产/做 labeled regression，但报告标注“不再盲测”，不能覆盖原始 batch |
| R5 | Examiner 单题 semantic miss | 保存该题 `model-recall-insufficient`（或平台未完成，依证据），继续后续题；不能提前终止整批 |
| R6 | 只读代理/运行时中止 | 已执行题与未执行题分离；剩余题不伪造结果；状态 `platform-runtime-incomplete` 并记录四层 failure layer |
| R7 | 丢失上下文/换会话 | 新 session/batch ID；保留旧 batch，不拼接成一个完整 PASS。只读重试不增加 semantic start；fresh modeling 需新授权 |
| R8 | unknown 对照 | 冻结答案明确 unknown 且 Examiner 正确保留 → 可通过；Examiner 无依据补猜 → 不通过或待复核，按证据归因 |
| R9 | cleanup/interruption | 停止所有子进程、socket、private bind、report sink；owner 明确的临时文件删除，freeze/review/report/failure/cleanup evidence 留存；未知写入不盲删 |

## 6. v3 批次验收和语义质量（L0/L1）

### L0 Runtime

在获用户授权且 008B（含 `r3-0-008b-staged-real.yaml` 双重门所列 R3.0-009 stage-3 机械增量）/006 前置完成后执行一次真实批次：只启动一个 Platform Examiner hidden batch，确认 `source-examiner` 从未启动；Runner/Acceptance 记录固定顺序、每题 report、tool/read-only scope、已执行/未执行和终态。L0 只回答“运行合同是否存活、证据是否完整”，不判业务答案质量。

### L1 Modeling quality

独立 Acceptance 读取保留 freeze、材料依据、模型绑定和 Platform reports，逐题判四态，另填四层 failure layer。至少覆盖：全景跨切片/跨 Ontology 关系、一个切片内规则和值语义、一个 mapping chain 语义支撑、正确 unknown。Acceptance 不读 CQ 私聊、不调用 write、不修模型；题目待复核不得改判为模型失败。SQL 实际结果、语义知识授权和 RDF 无业务行分别引用 006/008B 证据，不由 L1 CQ verdict 替代。

L1 完整 PASS 条件：本批所有应验收题均有有效裁决；没有 `question-answer-review`、`model-recall-insufficient`、`platform-runtime-incomplete`、未执行或越权 scope；所有报告能追到冻结 question ID/version 和 D5 model binding。题量只由获批 hidden 列表驱动，不以推荐范围作门。

## 7. L2/L3 和旧合同回归

| 层级 | 范围 | 通过口径 |
| --- | --- | --- |
| L2 | 对同一获批输入使用 fresh batch/session 重复生成/冻结/只读验收；比较题目覆盖、隔离证据、session identity 和逐题状态 | 差异可解释；不能把两个 session 合成一个完整 batch PASS；失败层可定位 |
| L3 | 仅在用户要求产品化时检查长期题库、UI、跨 run 版本治理等 | 本需求不把 L3 作为前置，当前只记录 `not in scope` |
| R2.3 | 运行既有 formal 任务及旧 `test_r23005_*`/`test_r23006_*` 合同，重点是 Source Examiner、逐题 fresh、Acceptance ticket、failure enum、旧 capability 广告 | 旧证据和行为不变；新 011 参数未显式选择时无 CQ 分支 |
| 008B/009 | staged artifact、stage3 slot、approval、value materialization、009 candidate/decision binding 的现有测试 | 只证明关联合同不回归；不能追溯为 011 语义 PASS |

## 8. 判定、证据与完成门

需求决策追踪：D1 → M7/R1；D2 → M6/M8；D3 → I1–I5；D4 → M9/R3；
D5 → M11/M12/M15/I6；D6 → R8/L1；D7 → R2/M16/L1；D8 → R4–R7；
D9 → M1–M5/M13/旧合同回归；D10 → L0/L1/L2/L3 分层结果。


每轮报告分别写：

- 机械/隔离：PASS、REVISE 或 BLOCKED，附 reason code 和可重试路径；
- L0 Runtime：是否启动成功、是否有未执行题、是否有 source-examiner、cleanup 状态；
- L1：四态逐题表、coverage、evidence refs、failure layer、model binding；
- L2/L3：单独结论，不倒置前层；
- 外部依赖/授权：未执行、失败和未授权明确区分。

`question-answer-review` 不计为模型失败，但也不计为通过；未执行不计为通过。平台/基础设施失败不得推导模型质量失败，机械 PASS 不得替代 L1。当前本测试计划不填写真实运行 PASS。

## 9. 清理和残余风险

每个 fixture/run 使用唯一 run root 和 owner；先保存 intent/receipt/delivery/report/failure/cleanup evidence，再清理临时资源。workspace owner 不明或写入状态未知时保留并报告。外部模型 API、bubblewrap、只读代理、PostgreSQL/查询 gateway 和用户授权是运行前置；此处只记录它们的阻塞层，不以 mock 结果宣称真实语义通过。

## 10. 计划评审记录（由主 Agent 填写）

| 项目 | 记录 |
| --- | --- |
| plan review | Round 1 REVISE：H1外层输入致命边界、H2 CQ生命周期均accepted-high并已修订；Round 2 专项复审 PASS；Round 3 REVISE：H1 T3 run-fallback超时、H2 scenario map 强制节均accepted-high并已修订（M6/M12/R1/I3、DC改名、L0前置）；Round 4 专项复审 PASS |
| implementation | 待实现；本轮未修改产品代码 |
| independent test | 功能测试 Round 1 已执行（2026-09-09，机械/隔离 REVISE：F1/F2 High）；复测 Round 2 已执行（2026-09-09）：F1–F6 FIXED，新发现 F7 High → 仍 REVISE；复测 Round 3 已执行（2026-09-09，仅变更面）：F7 FIXED（前台准入门 + 真实链路闭合）、R4 非盲测标注 FIXED、`pass`+layer 守卫闭合 → **机械/隔离 PASS**；L0/L1 BLOCKED（授权 + 008B 双重门 + 真实建模 start 未满足）；未启动真实 modeling start，无语义质量结论。详见下方 Round 1 / Round 2 / Round 3 记录 |
| semantic quality | 待 L1；无真实问题、参考答案、分组或模型证据可宣称 |

### Round 1 — 独立计划评审（2026-09-08）

结论 REVISE；主 Agent 核对源码后接受 H1/H2，修改设计 §3.2 和 M7/M12/R1。
H1 验证点：过期/错误 CQ 审核只拒当前输入，CLI/FIFO同run下一条合法输入可成功；不能以仅测validator代替事件循环存活。
H2 验证点：CQ跨全景审核、切片审核和冻结修订始终复用同一session；仅最终生产handoff后一次terminal，整体可settle。
这是一轮计划评审，不是已执行的功能测试。认证交接和受限只读proxy/回收仍须实现与L0测试证明。

### Round 2 — H1/H2 专项独立复审（2026-09-08）

结论 PASS；两项 accepted-high 已闭合，未发现剩余 Critical/High。复审覆盖设计 §3.2 的
CQ 窄输入拒绝、同session跨阶段继续、提前terminal可恢复拒绝及最终交付一次terminal，
并核对 M7/M12/R1 对应验证要求。Round 1 记录保留。

本轮文档检查：三个文档的 Markdown 链接/代码围栏、D1–D10 决策追踪及 diff 格式检查通过。
未执行产品代码测试、服务重启、L0/L1 或真实 semantic modeling start；不将文档检查计为实现或语义通过。

### Round 3 — 独立复审（2026-09-08，应用户要求按设计规范复审）

结论 REVISE；主 Agent 逐项源码核实后接受两项 `accepted-high` 并修订设计 §3.2/§3.3/§3.4/§7
与本计划 M6/M12/R1/I3，另将 §2 文档用例 ID 改为 DC 前缀以消除与需求决策 D1–D10 的二义。

- H1 验证点：CQ 审核/handoff 等待窗口不计入 `run-fallback-timeout` 的累计 active 时钟
  （`runner.py:1843/4913/5683`），等待超过默认 5400 秒后 run 仍可恢复；T3 对无等待真实停滞
  的保护不回退（对应 R1 新增断言）。
- H2 验证点：scenario map 的 `cross_slice_competency_questions` 节只引用公开投影题或显式
  置空并记录覆盖缺口；生产角色新撰跨切片题干被拒（对应 M6/I3 新增断言）。
- 随轮确认：`cq-acceptance` 不写 StartLedger/不消耗 semantic start（M12）；011 L0 前置含
  008B 双重门所列 R3.0-009 stage-3；public projection 采用 per-role 只读目录 bind；011 题池
  不登记平台资源、`competency_question_ids` 留空。

本轮文档检查：修订面 diff 与链接检查通过。未执行产品代码测试、服务重启、L0/L1 或真实
semantic modeling start；不将文档检查计为实现或语义通过。

### Round 4 — H1/H2 专项独立复审（2026-09-08）

结论 PASS；Round 3 两项 accepted-high 均闭合，修订未引入新 Critical/High。复审经真实代码
执行验证：`validate_scenario_map` 对“置空”与“引用公开投影题”均返回无 issue；T3 排除记账不新增
`_latch_formal_candidate_failure` 调用点且等待窗口只延后不消除真实停滞计时；public projection
目录 bind 与 `runtimes/codex.py` 既有 staged-decision bind 先例同构。次要记录（不计发现，留
实现/测试落实）：重叠等待窗口去重 + R1 混合用例、CQ 等待访谈输入同为等待态、投影外检放
Runner 侧、置空缺口落 acceptance batch 报告字段、验收批次 LLM 调用按“只读验收”口径在授权
台账留痕待实现确认。Round 1–3 记录保留。

本轮文档检查：变更面 diff 与链接检查通过。未执行产品代码测试、服务重启、L0/L1 或真实
semantic modeling start；不将文档检查计为实现或语义通过。

### Round 1 — 独立功能测试（2026-09-09，独立需求测试 agent）

**总体结论**：机械/隔离 = **REVISE**；L0 Runtime = **BLOCKED**；L1 = **BLOCKED**；L2 = 未执行；
L3 = `not in scope`。本轮未启动真实 modeling start、未调用真实 LLM/外部 API、未消耗 semantic
start 授权，因此**没有任何语义质量结论**；未执行不计为通过。

- **机械/隔离 REVISE 的 reason code**：
  - `cq_hidden_exposed`（F1，High）— Runner 侧从不登记 `_exposed_to`，"展示即永久公开"在真实链路上不可执行；
  - `cq_freeze_unreachable`（F2，High）— `freeze_cq_question_pool` 无任何产品触发路径，真实 run 永远不会产生 `competency-questions/frozen/<id>.json`，`cq-acceptance` 端到端不可达；
  - `cq_model_binding_missing`（F3，Low-Medium）— `AcceptanceBatchPacket.build` 不交叉核对 `model_binding.batch_id`/`freeze_digest`；
  - `cq_freeze_schema_mismatch`（F4，Low-Medium）— `competency_questions.py:1282` 死代码守卫，四态与四层枚举错配；
  - 记录级（F5/F6）— legacy run 的 CQ 外层输入实际走类型化拒绝而非注释所述致命路径；cleanup 未删除 owner 可证明的 CQ private temp。
- 可重试路径：先修 F1/F2（其余 F3–F6 可一并修），再复测本轮；L0/L1 在授权与 008B 前置满足后另行排期。

#### A. 轮次与代码状态

| 项 | 记录 |
| --- | --- |
| 代码版本 | branch `main` @ `ec5c690` + 未提交工作区（R3.0-011 实现未提交）；本轮未修改任何产品代码、未 commit |
| 基线（非本轮产生） | `AGENTS.md`、`CLAUDE.md`、两份 011 文档、`requirements-v3.0.md` 的既有改动与未跟踪 `.codex/agents/`；实现侧新增/修改文件为被测对象 |
| profile/task | `modeling_team/profiles/r3-0-011-competency-question.yaml` + `modeling_team/tasks/r3-0-008b-staged-real.yaml`；回归另用 `r3-0-002-*` 与 R2.3 旧 profile/task |
| 授权 scope | 无真实用户授权；只有机械/fixture/隔离探针；未触碰 PostgreSQL/只读代理/bubblewrap 真实链路 |
| run/batch/session ID | run root 全部为本轮独占的 `workspaces/modeling-runs/r3011probe-<sha256[:10]>`，用后即删；batch ID（`batch-probe`/`batch-happy-run`/`batch-drift-run`/`batch-r9` 等）仅存在于 `/tmp` fixture 与被删 run root |
| role source manifest | 见 P14：CQ = 四个业务输入 + `modeling_team/references/r3-0-011-competency-question-contract.json`；coordinator/modeling/protocol 无任何 CQ/011 路径；全 manifest 无 tester-only/参考答案路径 |
| artifact digest | `batch-happy-run` freeze_digest `sha256:5a0e7e1a…86a`、report `batch-report.json`（0600）、packet 记录 digest `087dcb44…3ce`；`batch-drift-run` freeze_digest `sha256:437e12a4…94a` |
| cleanup owner | 本轮自建 run root、ledger root 与 `/tmp` fixture 全部由本轮删除（见 G） |

#### B. 已执行命令与结果

```bash
uv run --project backend python -m pytest -q modeling_team/tests/test_r3011_acceptance.py \
  modeling_team/tests/test_r3011_contracts.py modeling_team/tests/test_r3011_cq_lifecycle.py \
  modeling_team/tests/test_r3011_runner_wiring.py
# → 77 passed in 0.99s
uv run --project backend python -m pytest -q modeling_team/tests/test_r30002_runner_wiring.py \
  modeling_team/tests/test_r30002_scenario_map.py modeling_team/tests/test_r30008b_runner_wiring.py \
  modeling_team/tests/test_r30008b_staged_decisions.py modeling_team/tests/test_r30009_runner_wiring.py \
  modeling_team/tests/test_r30009_unified_graph.py
# → 147 passed in 1.98s
uv run --project backend python -m pytest -q modeling_team/tests/test_r23005_contracts.py \
  modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py
# → 97 passed, 78 subtests passed in 4.21s
uv run --project backend python -m pytest -q modeling_team/tests
# → 7 failed, 1283 passed, 1 skipped, 318 subtests passed in 47.25s
cd backend && uv run pytest -q
# → 1006 passed, 36 skipped in 54.31s
```

- 7 个失败全部集中在 `modeling_team/tests/test_deepseek_codex_runtime.py` 的权限负例，且仅因
  测试 shell 环境已导出 `DEEPSEEK_API_KEY`（len=35）：`env -u DEEPSEEK_API_KEY` 重跑同文件
  → `21 passed`。**不计为产品缺陷**，但它是环境敏感性：该文件在带 key 的环境下会误报。
- 环境注意：§1 推荐命令里的 `uv run --project backend pytest -q modeling_team/tests/...`
  会因 `modeling_team` 不在 `sys.path` 而 collection error；须用
  `uv run --project backend python -m pytest …`（仓库根为 cwd）或进入 `backend` 后
  `uv run pytest ../modeling_team/tests/...`。`cd backend && uv run pytest` 只收集
  `backend/tests`（`testpaths = ["tests"]`，1042 collected），**不覆盖 `modeling_team/tests`**。

#### C. 计划用例逐项结果

| ID | 结果 | 证据/说明 |
| --- | --- | --- |
| DC1 | PASS | 需求/设计/计划互引（design:4、design:234、plan:3/5）；D1–D10（requirements:829 起）、四态（requirements:850/854/881，design:202）、四层（requirements:853）齐全。记录：`requirements-v3.0.md:202` 状态仍写"待实现、待独立验收"，与工作区已实现状态不一致（文档状态更新归主 Agent） |
| DC2 | PASS | design §1 插入 008B CQ 阶段、§3.4 public projection 边界、§6 L0 前置沿用 008B 双重门 + 006 授权；006/008A/009 只引用不重建 |
| DC3 | PASS | `test_m2_legacy_smoke_roster_has_no_cq_role_or_operation`、`test_m13_v3_child_seam_rejects_a_legacy_packet`；legacy run root 被 `cq-acceptance` 以 exit 2 拒绝（P7a） |
| DC4 | PASS | 1 题与 40 题草稿均发布成功并带 `advisory_count_feedback`（P13b）；3 切片各 1 题冻结通过（P13c）；批准只能来自 outer `cq_review`，CQ 仅有 `cq_publish_question_draft` 能力（P11a） |
| M1 | PASS | 011 selector 下 prepare 成功、roster 含 CQ 且无 examiner/acceptance 角色（P11d）；不启动 Agent（CapturingAdapter 无 start） |
| M2 | PASS | 002/008B/009 回归 147 passed；legacy run `_competency_questions=False`（P18a）。记录：F5 |
| M3 | PASS | 011 profile/task 加载成功（额外 CQ 不被固定三角色误拒）；typed reject 面由 `test_r3011_contracts` 覆盖 |
| M4 | PASS | P14a–P14d：CQ 与 Modeling 同四业务输入；生产角色无 CQ/011 路径；全 manifest 无 tester-only/答案路径；CQ 不在通信边 |
| M5 | PASS | 仅 CQ 广告 `cq_publish_question_draft`（P11a）；其余角色无 CQ 能力、无 hidden-batch 字样（P11b/c）；草稿字段错误只拒当前草稿且 run 存活（P9a/P9c） |
| M6 | PASS | 投影只含获批 public 题（P2）；scenario map 三字段强制节 9 个对抗负例全拒（P2a–P2i），生产新撰跨切片题干被拒 `cq_public_projection_missing`，置空记 `coverage_gap: true`，拒绝不回显题干 |
| M7 | PASS | P17a–P17h：CQ 动作在已知 outer 动作门内；stale digest/content_version/schema/未知 question_id 全部走 `cq-input-rejected`（不触 `receive_outer` 致命边界）；malformed 行走 `outer-input-rejected`；run/session ID 不变；下一条合法审核成功；拒绝不带题干。stdin 与 FIFO 共用 `_handle_foreground_message`（`__main__.py:302/319/335`）。记录：`revision` 只校验正整数（informational） |
| M8 | REVISE | 全景 hidden 预留、切片只读投影、审核后投影、freeze 校验均通过（P2/P3/P13）；但"曾展示题不能转 hidden"在 Runner 侧不成立 → F1 |
| M9 | PASS | freeze snapshot digest 闭合、篡改/改写/缺 digest 均拒（P3a–P3d）；`freeze-9999` 未冻结被拒（P7 系列） |
| M10 | PASS | P13a–P13c：无固定题数/切片数/Agent 数硬门 |
| M11 | REVISE | 缺状态/越权/漂移拒绝（P4b–P4i）；freeze 不绑定 workspace；但 packet 层不交叉核对 binding 的 batch/freeze → F3（CLI 层已有核对，P7f exit 2） |
| M12 | PASS（fixture 级） | CLI 端到端 12 例：legacy root/缺 root/delivery 未就绪/binding batch 或 freeze 不匹配/freeze 篡改/未冻结/selector off → 全部 exit 2 且不写报告；happy path exit 0、目录 0700 + 文件 0600、`full_pass=false`、全部题 unexecuted、session 记 not-started 与授权阻塞、报告/包记录均无题干与 `answer_points`、`start_ledger_write=false`、不新增 run root；drift 后仍 exit 0 且不复用旧 PASS。受 F2 影响，真实链路不可达 |
| M13 | PASS | `instructions-v3.md` 两份存在且 legacy prompt 保留（P15a/P15b）；v3 为单批次合同（P15f）、四态齐全（P15g）；CQ 提示含六阶段（P15e）。记录：v3 提示只点名 3/4 层（该提示说明其可能使用的层，informational） |
| M14 | PASS | 证据包需可读 bytes + digest 一致 + review version（P16a 及负例）；空 entries 被接受但只能导出待复核（informational）；纯待复核允许空 layer 且不能改判 modeling-quality（P16h/P16i）。记录：F4 |
| M15 | PASS | P4i 漂移上报 `["ontology-1"]`、同状态重查无漂移（P4j）；P7g 漂移后 exit 0 记录新 batch，不复用旧 PASS |
| M16 | PASS | `build_batch_report` coverage gaps（empty hidden set / slice 无隐藏题 / 跨切片缺口 / 漂移）；空隐藏集永不 PASS（`batch_report_is_full_pass`） |
| I1 | PASS | 生产角色 `role_sources` 与 bind 面均无 CQ private/frozen 路径（P14b、P8c）→ 物理不可读 |
| I2 | PASS | P8b/c/d/e：CQ=private+reviews 只读；coordinator/modeling/protocol=仅 public 只读；examiner/acceptance/source-examiner=无任何 CQ bind |
| I3 | PASS | P10b：被拒 hidden 草稿文本在全 run root 无残留；P10c：审核批准前无投影文件；报告/包记录无题干/答案/`answer_points`；拒绝信封不带题干（P17d、P2b/P2d） |
| I4 | PASS | P11a–P11d 能力广告与 role 绑定准确；CQ 无 platform 工具；生产角色无 hidden packet 能力 |
| I5 | **FAIL → F1** | validator 端 `cq_hidden_exposed` 有效（probe6 P3e），但 Runner 不登记 `_exposed_to`；实测"先 public 投影给生产角色、再冻结为 hidden"成功（probe4 VERDICT: LEAK POSSIBLE） |
| I6 | PASS | 越权 Ontology 拒（P4d）、空 Ontology 列表拒（P4e）、缺 workspace/graph state 拒（P4b/c）、漂移上报（P4i） |
| R1 | PASS | P1a：9000s 审核等待窗口在 10000s run 内不 latch、`excluded=9000.0`、等待窗口证据已记录；P1b：6000s 真实停滞仍 latch（`FormalCandidateProgressTimeout: run fallback timeout exceeded 6100 active seconds`）；P1c：重叠窗口 union 去重为 200s、5300s+200s 才 latch |
| R2 | PASS | stale/未知题/schema 错误 → `cq_review_stale` 类型化拒绝；冲突走 `question-answer-review` 且保留（P16h）；coverage gap 保留 |
| R3 | PASS | 冻结修订=新版本，篡改旧版本被 digest 拒（P3a–P3c）；旧 review/freeze 只读保留（P19c） |
| R4 | **FAIL → F1** | 因 Runner 不登记 exposure，"受影响题转 public + 标注不再盲测"的触发条件在本实现中不存在 |
| R5 | PASS（机械面） | 逐题 verdict 可表达 `model-recall-insufficient` 且不阻断批次（validate 层接受）；真实单题语义 miss 属 L1，未执行 |
| R6 | BLOCKED | 阻塞层：真实 runtime/只读代理/bubblewrap。机械面已验：`platform-runtime-incomplete` 可携带四层归因记录（validator 接受，另见 F4） |
| R7 | BLOCKED | 阻塞层：真实多 session/LLM。已验机械面：`cq-acceptance` 只读、`start_ledger_write=false`、不消耗 semantic start（P7d）；fresh modeling 需新授权（授权边界记录） |
| R8 | PASS（机械面） | freeze 强制 `unknown` 字段、证据包需依据与 digest；"Examiner 无依据补猜"的判定属 L1，未执行 |
| R9 | PASS（含 F6） | P19a–P19f：cleanup 停 adapter、0440/0444 只读文件不阻塞、`reviews/`+`frozen/` 证据留存、未知 owner 写入不盲删、二次 cleanup 幂等。记录：`competency-questions/private` 的 owner 可证明 temp 未删除（design §5）→ F6 |

#### D. 独立探针（本轮自写，非仓库测试）

- P1（R1/T3）：等待窗口排除、真实停滞保护、重叠窗口去重（见 R1 行）。
- P2（M6/I3）：投影内容 + scenario map 强制节 9 个对抗负例。
- P3（M9/D4）：freeze 篡改/改写/缺 digest/`_exposed_to` 校验。
- P4（M11/I6）：model binding 形状/越权/漂移（并暴露 F3）。
- P6/P7（M12/F3）：packet seam + `cq-acceptance` CLI 端到端 12 例（含 host-only 权限与零 StartLedger 写入）。
- P8–P11（I1–I4/M5）：bind 面、泄漏负例、能力广告。
- P12（I5/F1）：真实 Runner 链路"先 public 后 hidden"→ LEAK POSSIBLE。
- P13–P16（M10/M13/M14/DC4）：题量边界、提示词、证据/裁决边界、role_sources。
- P17–P19（M7/R9/F5/F6）：foreground/FIFO 共用准入路径、legacy 分派、cleanup 行为。

#### E. 缺陷（按严重度）

**F1（High）— "展示即永久公开"未被 Runner 执行（I5/R4/M8）**
- 复现：`uv run --project backend python /tmp/…/probe4_i5.py`（发布 public 草稿 → outer `cq_review` 批准 → Runner 写出 `competency-questions/public/public-projection-0001.json`（生产角色可见）→ `runner.freeze_cq_question_pool(..., proposed_visibility="hidden")`）。
- 实际：freeze 成功，`visibility = {"cq-pan-shown": "hidden", "cq-pan-blind": "hidden"}`；probe 输出 `VERDICT: LEAK POSSIBLE — a question already projected to the production roles was frozen as hidden`。
- 期望（design §3.3 第 4 步、需求 D2、计划 I5）：已投影给任一生产角色的题永久转 public（或 reject），并保留泄漏证据。
- 根因：`grep -n "_exposed_to" modeling_team/runner.py` → 无匹配；该字段只在 `competency_questions.py:596-614` 被校验，但没有任何调用方写入；草稿级发布是精确字段校验，带 `_exposed_to` 的草稿反被 `cq_freeze_schema_mismatch` 拒绝（probe3 P9a：`retry=send exactly the fields ['answer_points', …]`），守卫处于休眠状态。
- 影响面：hidden 题可能已被 Coordinator/Modeling/Protocol 看过 → L1 blind 验收失效；R4 的"转 public + 标注不再盲测"无法触发。
- 修复建议：Runner 在投影/投递时刻记录 `question_id → exposed roles`（evidence + 内存态），freeze 前据此改写 visibility 为 public 并落泄漏证据，或在提交 hidden 时 reject 该题。

**F2（High）— freeze 无产品触发路径，`cq-acceptance` 端到端不可达（M12/M8）**
- 证据：`grep -rn "freeze_cq_question_pool" modeling_team --include=*.py | grep -v tests/` → 仅 `runner.py:5402` 定义，无调用点；CLI/outer 分派只接受 `cq_interview`/`cq_review`/`cq_handoff_complete`（`__main__.py:146`）；`_handle_cq_review` 在全景审核后置 `awaiting-slices`、切片审核后置 `slice-draft`，均不冻结。
- 实际：真实 run 无法产生 `competency-questions/frozen/<id>.json`，而 `cq-acceptance` 启动硬性要求该文件（`__main__.py` `_run_cq_acceptance`，缺失 → `cq_selector_incompatible` exit 2）。
- 期望（design §3.2 生命周期、§4.0/4.1）：最终分组时由 Runner/CQ/Delivery 触发 freeze，随后验收可启动。
- 结论：机械合同与 CLI 均按 fixture 验证通过，但端到端链路在本实现中断；L0 无法在现状态下启动。

**F3（Low-Medium）— `AcceptanceBatchPacket.build` 不交叉核对 model binding 的 batch/freeze（M11）**
- 证据：probe1 P4f/P4g、probe2 P6：packet `freeze_digest=sha256:aaa…` vs binding `freeze_digest=sha256:bbb…`、packet `batch_id=batch-probe` vs binding `batch_id=batch-other`，`build` 均成功。
- 期望（design D5、计划 M11）：缺状态/越权/漂移/错绑都应拒 batch；CLI 层已核对（P7f exit 2），缺口在文档化的 packet 接缝（纵深防御）。
- `validate_model_binding`（`competency_questions.py:1033-1123`）只校验形状与授权 scope，不比对调用方给出的 freeze。

**F4（Low-Medium）— 死代码守卫使非 PASS 四态可带空 failure_layer（M14/R5/R6）**
- 证据：`competency_questions.py:1282` `if verdict["verdict"] in CQ_EVIDENCE_BACKED_FAILURE_LAYERS and layer is None:` —— 左侧是四态名（`model-recall-insufficient`/`platform-runtime-incomplete`），右侧元组（`:87`）是四层名，永不匹配。实测 `validate_acceptance_verdict({... "verdict": "model-recall-insufficient", "failure_layer": None ...})` 与 `"platform-runtime-incomplete"` 均被接受。
- 期望（`agent-packages/acceptance/instructions-v3.md`）：这两个状态必须归因 `modeling-quality`（前者）/对应运行层（后者），否则批量报告无法定位失败层。
- 修复：改为与四态集合比较，或直接对这两态强制非空 layer。

**F5（Low，记录级）— legacy（非 011）run 的 CQ 外层输入行为与注释不符（M2/M7）**
- `__main__.py:_handle_cq_outer_message` 文档字符串称"未选择 011 的 run 保持 legacy 致命路径"，但 `TeamRunner.handle_cq_outer_input` 恒存在，实测 legacy run 的 `cq_review` 行返回 `returned=True` 且输出 `{type: cq-input-rejected, reason_code: cq_selector_incompatible, retry: restart the run with the R3.0-011 Task selector enabled}`，不再进入 `receive_outer` 致命边界。
- 行为是安全的（run 存活、类型化拒绝、带重试指引），属文档/实现不一致：应改注释，或按注释对非 011 run 返回 `False`。

**F6（Low）— cleanup 未删除 owner 可证明的 CQ private temp（R9）**
- 证据：probe7 P19d：cleanup 前后 `competency-questions/private/` 均为 `['draft-0001.json']`（0440）；`cleanup()`（`runner.py:6951-7042`）只删 `secrets/`。
- 期望（design §5:216）：删除 owner 可证明的 private temp/packet staging；保留冻结快照、历史 review、reports、failure/recovery/cleanup evidence。
- 影响：纯卫生问题，无泄漏（该目录从不进入任何生产角色 bind 面）。

**Informational（不计发现）**：v3 acceptance 提示只点名 3/4 层（其措辞为"可使用的层"）；空 evidence `entries` 被接受但只能导出待复核、永不 PASS；`batch-packet.json` 只存 `canonical_digest`+`schema_version`（无题干/答案，0600）；`revision` 只校验正整数、不构成单调门（staleness 由 `content_version`/`content_digest` 承担）；`requirements-v3.0.md:202` 状态未更新。

#### F. L0/L1/L2/L3

- **L0 Runtime：BLOCKED（未执行）**。阻塞层：R3.0-006 用户授权未取得、008B 双重门（含 R3.0-009 stage-3 机械增量）前置未满足、真实 modeling start 未启动；另受 F2 影响（freeze 文件无法在真实 run 中产生）。
- **L1 Modeling quality：BLOCKED（未执行）**。同一阻塞层；本轮无真实问题、参考答案、分组或模型证据，**不作任何语义质量声明**，不填四态逐题表。
- **L2 Repeatability：未执行**（依赖 L0/L1）。**L3：`not in scope`**。
- 外部依赖/授权：未执行 = L0/L1/L2；失败 = F1–F6；未授权 = 真实批次验收。

#### G. 清理与残余风险

- 本轮自建 run root/ledger（`r3011probe-*`）已全部删除；`workspaces/modeling-runs/` 现存目录与本轮无关。
- `/tmp` 探针与 fixture（`/tmp/r3011_probe*.py`、`/tmp/r3011-cli-probe/`）在本轮结束后删除。
- 残余风险：F1+F2 使"public/hidden 隔离 + 批次验收"的真实闭环未被证明；F3/F4 削弱报告纵深；R5–R8 的真实运行时/多 session 行为只有机械面证据。修复后须复测本轮（优先 F1/F2 及其回归面 M8/M12/I5/R4/R9），再排期 L0。

### Round 2 — 独立功能测试复测（2026-09-09，独立需求测试 agent）

**总体结论**：机械/隔离 = **REVISE**（Round 1 的 F1–F6 全部 **FIXED**，复测发现新 High 缺陷 **F7**，
使 F2 的真实触发路径仍不可达）；L0 Runtime = **BLOCKED**；L1 = **BLOCKED**；L2 = 未执行；
L3 = `not in scope`。本轮未启动真实 modeling start、未调用真实 LLM/外部 API、未消耗 semantic
start 授权，因此**没有任何语义质量结论**；未执行不计为通过。

- 复测 reason code：`cq_freeze_unreachable`（F7，High）— `cq_freeze` 已进入窄 CQ 分派集合
  `_CQ_OUTER_ACTIONS`，但没有进入前台共享准入门 `_KNOWN_OUTER_ACTIONS`，Delivery host 经真实
  CLI/stdin/FIFO 发出的 freeze 行被 `outer-input-rejected` 拒绝，freeze 快照无法在真实 run 中产生。
- 可重试路径：把 `cq_freeze` 加入 `modeling_team/__main__.py` 的 `_KNOWN_OUTER_ACTIONS`，并补一条
  走前台路径的仓库测试（现有 011 测试全部直接调用 Runner 入口，无一条覆盖前台准入）。F7 修复后
  须复测 F7 本身与 M8/M12 的真实触发面；F1–F6 的修复不需重测。

#### A. 轮次与代码状态

| 项 | 记录 |
| --- | --- |
| 代码版本 | branch `main` @ `ec5c690` + 未提交工作区（R3.0-011 实现；`__main__.py`/`runner.py`/`acceptance_runtime.py`/`competency_questions.py` 等相对 Round 1 又有修改）；本轮未修改任何产品代码、未 commit |
| 基线（非本轮产生） | `AGENTS.md`、`CLAUDE.md`、两份 011 文档、`requirements-v3.0.md` 既有改动与未跟踪 `.codex/agents/` |
| profile/task | `modeling_team/profiles/r3-0-011-competency-question.yaml` + `modeling_team/tasks/r3-0-008b-staged-real.yaml`；回归另用 002/008B/009 与 R2.3 旧 profile/task |
| 授权 scope | 无真实用户授权；只有机械/fixture/隔离探针；未触碰 PostgreSQL/只读代理/bubblewrap 真实链路 |
| run/batch/session ID | run root 全部为本轮独占的 `workspaces/modeling-runs/r3011r2-<sha256[:10]>`，用后即删；batch ID 形如 `cq-batch-0001`，仅存在于已删除的 run root |
| artifact digest | Runner 产出真实 run root 的 freeze digest `sha256:8606c7f6…8ac8`（B6/B13 一致）；第二份 freeze `sha256:e79b94b4…df78` |
| cleanup owner | 本轮自建 run root、ledger root 与 `/tmp` probe 全部由本轮删除（见 J） |

#### B. 已执行命令与结果

```bash
uv run --project backend python -m pytest -q modeling_team/tests/test_r3011_acceptance.py \
  modeling_team/tests/test_r3011_contracts.py modeling_team/tests/test_r3011_cq_lifecycle.py \
  modeling_team/tests/test_r3011_runner_wiring.py
# → 89 passed in 1.64s
uv run --project backend python -m pytest -q modeling_team/tests/test_r30002_runner_wiring.py \
  modeling_team/tests/test_r30002_scenario_map.py modeling_team/tests/test_r30008b_runner_wiring.py \
  modeling_team/tests/test_r30008b_staged_decisions.py modeling_team/tests/test_r30009_runner_wiring.py \
  modeling_team/tests/test_r30009_unified_graph.py
# → 147 passed in 2.35s
uv run --project backend python -m pytest -q modeling_team/tests/test_contracts.py \
  modeling_team/tests/test_r23002.py modeling_team/tests/test_r23003_incremental_contract.py \
  modeling_team/tests/test_r23003_modeling_readonly.py modeling_team/tests/test_r23003_revision_contract.py
# → 88 passed, 41 subtests passed in 2.21s
env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest -q modeling_team/tests
# → 1302 passed, 1 skipped, 318 subtests passed in 49.06s
cd backend && uv run pytest -q
# → 1006 passed, 36 skipped in 54.33s
```

- 环境敏感性复现（同 Round 1，不计产品缺陷）：带 `DEEPSEEK_API_KEY`（len=35）跑
  `test_deepseek_codex_runtime.py` → `7 failed, 14 passed`；`env -u DEEPSEEK_API_KEY` 下随全量通过。
- 命令形态注意（同 Round 1）：须用 `uv run --project backend python -m pytest …`（仓库根为 cwd）。
- 探针自身修正（非产品问题）：`r2_probeA_f1_f2.py` 的 A4 用错证据路径（实际流为
  `evidence/cq-exposure.jsonl`，由 A2_fix A4/A4b 判 PASS）、A9 未先把全部题 decided，使未决守卫先于
  exposure 守卫触发；由 `r2_probeA3_stamp.py` A9' 判 PASS。实测守卫优先级：空池
  `cq_freeze_schema_mismatch` → 未决题 `cq_review_stale` → exposure `cq_hidden_exposed`。
  `r2_probeB_fixes.py` 的 C3（`pass` + `failure_layer=modeling-quality` 应被拒）为探针过严：validator
  只对 `question-answer-review` 禁止 modeling-quality 归因，`pass` 带层被接受（informational）。

#### C. Round 1 缺陷复测结论

| Round 1 缺陷 | 复测结论 | 独立证据（本轮自跑） |
| --- | --- | --- |
| F1 High "展示即永久公开"未被执行 | **FIXED** | A3：投影写出时 Runner 记录 `{"cq-pan-shown": ["coordinator","modeling","protocol"]}`；A5：已展示题再提案 hidden → `cq_hidden_exposed`（retry: keep the question public; a shown question is permanently public）；A6/A7：被拒草稿只留 `draft-0001.json`、无 freeze 快照；A8：run 继续接受 public 草稿；A2_fix A4/A4b：`evidence/cq-exposure.jsonl` 存在，事件 `question-exposed-to-production` + `reason_code: permanently_public` + roles；A3_stamp A9'：全部题 decided 后注入 exposure 再 freeze → `cq_hidden_exposed`，无快照；A11'：用户把该题改回 public 后同一 freeze 成功（`hidden_question_count: 0`） |
| F2 High freeze 无产品触发路径 | **FIXED（Runner + CLI 面）**，但前台准入被 F7 阻断 | B1：空池 → `cq_freeze_schema_mismatch`；B2：未决题 → `cq_review_stale`；B4：outer 分支 `{"action":"cq_freeze"}` → `{"type":"cq-frozen","freeze_id":"cq-batch-0001","hidden_question_count":2,"phase":"frozen"}`；B5：`frozen/freeze-0001.json` 权限 `0o100440`；B6：重载 digest 与 ack 一致 `sha256:8606c7f6…8ac8`；B7/B8：冻结池保留 panorama/hidden 与 slice scope，投影过的题为 public（D2）；B9：`cq-freeze` 证据事件；B10：二次 freeze 追加 `freeze-0002` 且 `freeze-0001` 字节不变；B11：篡改文件 → `snapshot_digest does not match the frozen file contents`；B12：真实 run root 含 `acceptance-v3/run-contract.json`（三参数 true）；B13–B18：`cq-acceptance` 在 Runner 产出的真实 run root 上 exit 0，报告集 0600，`full_pass=false`、`unexecuted=["cq-pan-h1","cq-slice-h1"]`、无题干/`answer_points`、StartLedger 零写入、run root 未变；B19/B20：delivery 未就绪 → exit 2 `cq_batch_scope_unauthorized`；未知 freeze id → exit 2 `cq_freeze_schema_mismatch` |
| F3 Low-Medium packet 不核对 binding | **FIXED** | `AcceptanceBatchPacket.build` 在 `batch_id` 或 `freeze_digest` 不一致时 raise `ChildRuntimeError("v3 acceptance model binding does not match this batch and freeze snapshot")`（`acceptance_runtime.py:443-451`）；CLI 层核对保持（B19） |
| F4 Low-Medium 死代码守卫 | **FIXED** | `competency_questions.py:88` `CQ_REQUIRED_FAILURE_LAYERS`：`model-recall-insufficient → ("modeling-quality",)`、`platform-runtime-incomplete → ("runtime/infrastructure","platform-contract")`；`validate_acceptance_verdict` 强制这两态 layer 命中要求（缺/错层 → `cq_freeze_schema_mismatch`），`pass`/`question-answer-review` 仍允许 null |
| F5 Low legacy 注释不符 | **FIXED** | `_handle_cq_outer_message` docstring 改为"非 011 run 得到类型化 `cq_selector_incompatible`，不是 crash"；行为复测不变（legacy `cq_review` → 类型化拒绝、run 存活） |
| F6 Low cleanup 未删 private temp | **FIXED** | E1–E7：`_cleanup_cq_private` 在 `cleanup()` 内执行，删除 owner 可证明的 `draft-0001.json`；symlink 与 fifo 按 `unknown-owner` 保留并在 `cq-cleanup` 证据上报；run root 外的 symlink 目标未被删；`frozen/`、`reviews/`、`public/`、`acceptance-v3/reports`、`evidence` 全部保留；二次 cleanup 幂等 |

#### D. 计划用例复测结果（受影响面 + 必要回归）

| ID | Round 1 | Round 2 | 证据/说明 |
| --- | --- | --- | --- |
| M8 | REVISE（F1） | **FIXED → PASS** | 原有全景 hidden 预留/切片只读投影/审核后投影/freeze 校验保持；新增已展示题不可转 hidden（A5、A9'） |
| M11 | REVISE（F3） | **FIXED → PASS** | packet seam 核对 + CLI exit 2 保持 |
| M12 | PASS（fixture 级） | **PASS（fixture + Runner 真实 run root）** | B13–B18 在 Runner 产出的 run root 上跑通 CLI；但 Delivery host 的前台触发仍断（F7） |
| I5 | FAIL（F1） | **FIXED → PASS** | 展示即永久公开在 Runner 侧生效；泄漏事实落 `evidence/cq-exposure.jsonl` |
| R4 | FAIL（F1） | **FIXED（机制面）+ 一处偏差** | 受影响题在 freeze 时被拒，用户改 public 后才能冻结，且不再进入 hidden 分母；泄漏事实有证据流。**偏差**：计划 R4 写的"报告标注'不再盲测'"无对应实现（代码无该字样；冻结快照会 pop `_exposed_to`）。新机制以"拒绝 + 用户改 public + 空隐藏集覆盖缺口"替代标注；需求原文（`requirements-v3.0.md:847`）只要求"受影响题不能再提供盲测证据"，未强制字面标注。是否补报告字段由主 Agent 裁决 |
| R9 | PASS（含 F6） | **PASS** | F6 修复后 E1–E7 |
| R1 | PASS | **PASS（回归）** | H1：9000s 审核等待全排除（`excluded=9000.0`）；H2：重叠窗口 union（100–300 与 200–400 → 300，非 400）；H3：`_check_run_fallback_timeout` 仍减去 CQ 窗口；H4：默认 5400s 未变 |
| M10/DC4 | PASS | **PASS（回归）** | H5：40 题 panorama 草稿被接受（`advisory_count_feedback: null`）；H6：1 题切片草稿被接受；无固定题数/切片数硬门 |
| M6 | PASS | **PASS（回归，对抗负例补齐三字段合同）** | D2 I1：逐字公开引用无 issue；I2/I3：新撰题干、hidden id、真 id 改写、slice id 全部 `cq_public_projection_missing` 且不回显新撰文本；四字段与重复引用 → `cq_freeze_schema_mismatch`；I4：显式置空 → `coverage_gap: true` 记录缺口 |
| M16 | PASS | **PASS（回归）** | 同 I4（空隐藏集/空节 → 记录缺口，不作异常、不产生 PASS） |
| I3 | PASS | **PASS（回归）** | H10：38465 bytes 共享证据流扫描无题干/答案文本；各拒绝信封不回显新撰文本 |
| I1/I2/I4 | PASS | **PASS（回归）** | H11：七个角色 bind 面（cq=private+reviews；coordinator/modeling/protocol=public 只读；examiner/acceptance/source-examiner=无任何 CQ bind） |
| M2/M7/DC1–DC3 | PASS | **PASS（回归）** | 002/008B/009 147 passed、R2.3 合同子集 88 passed + 41 subtests、011 全套 89 passed |
| M13 | PASS | **PASS（回归）** | 两份 v3 提示均列出全部四层（`modeling-quality`/`platform-contract`/`collaboration/routing`/`runtime/infrastructure`；acceptance 7 处、platform-examiner 2 处），Round 1 的"只点名 3/4 层"informational 已闭合 |
| R2/R3/R5/R8/M1–M5/M9/M14/M15/I6 | PASS | **PASS（未单独重跑）** | 由本轮 011 全套 89 passed 与全量 1302 passed 覆盖机械面；未发现回归 |

#### E. 本轮独立探针（自写，非仓库测试，用后已删）

- `r2_probeA_f1_f2.py` + `r2_probeA2_fix.py` + `r2_probeA3_stamp.py`：F1/F2 全链（exposure 记录、hidden
  负例、守卫优先级、freeze 追加/篡改、CLI 在真实 run root 上的正负例）。
- `r2_probeB_fixes.py`：F3 packet seam、F4 层强制、F5 legacy 分派、F6 cleanup（E1–E7）、D5=F7 断言。
- `r2_probeC_gate.py`：F7 前台准入门（G0–G5）。
- `r2_probeD_regress.py`：R1 等待窗口、M10 题量边界、I1/I2/I3 bind 与证据文本扫描。
- `r2_probeD2_map.py`：M6 scenario map 三字段合同对抗负例与显式置空缺口（I1–I4）。

#### F. 新缺陷 F7（High）— `cq_freeze` 不在前台准入门内，Delivery host 无法触发冻结

- 复现：011 run 内发布并批准 1 题 → 经前台共享路径（stdin 与 outer FIFO 共用
  `_handle_foreground_message`，`__main__.py:302/319/335`）发送一行 `{"action": "cq_freeze"}`。
- 实际：返回 `{"type": "outer-input-rejected", "code": "invalid_outer_input", "retryable": true}`，
  `competency-questions/frozen/` 为空；同一 `{"action": "cq_freeze"}` 直接交给
  `TeamRunner.handle_cq_outer_input` 则成功产出 `freeze-0001.json`（G3 vs G4/G5），证明缺口只在准入门。
- 期望（design §3.2 生命周期、D1、计划 M8/M12）：`cq_freeze` 是 Delivery host 的 host-only 动作，应与
  `cq_interview`/`cq_review` 一样经前台路径进入窄 CQ 分支。
- 根因：`_KNOWN_OUTER_ACTIONS`（`modeling_team/__main__.py:126-141`）缺少 `"cq_freeze"`，而
  `_CQ_OUTER_ACTIONS`（:148）含它；`_handle_foreground_message` 先按前者门控才到 CQ 分支。
  仓库 011 测试（7 处 cq_freeze 相关）全部直接调用 Runner 入口，无前台路径覆盖，故未拦截。
- 影响面：F2 的真实触发不可达 → 真实 run 无法产生 freeze 快照 → `cq-acceptance` 端到端仍不可启动；
  M8/M12 的"最终分组由 Delivery host 触发"未闭合。机械合同、Runner 逻辑与 CLI 本身已验证正确。
- 修复建议：把 `cq_freeze` 加入 `_KNOWN_OUTER_ACTIONS`，并新增一条走 `_handle_foreground_message`
  （或真实 CLI/FIFO）的测试，断言 `cq_freeze` 不被 `outer-input-rejected` 拒绝且 `cq_review` 仍正常。

#### G. Informational（不计缺陷）

- `pass` 裁决携带非空 `failure_layer` 被 validator 接受（只对 `question-answer-review` 禁止
  modeling-quality 归因）；如需"pass 必须空层"可再加一条守卫。
- freeze 守卫优先级：空池 `cq_freeze_schema_mismatch` → 未决题 `cq_review_stale` → exposure
  `cq_hidden_exposed`；未决守卫先于 exposure 守卫触发。
- exposure 事实只存在 `evidence/cq-exposure.jsonl` 与 Runner 内存态，冻结快照不含 `_exposed_to`
  （pop 掉），因此验收报告没有"曾被展示"字段（与 R4 偏差同一件事，见 D 行）。
- `revision` 仍只校验正整数，不构成单调门（staleness 由 `content_version`/`content_digest` 承担，同 Round 1）。
- `requirements-v3.0.md:202` 状态仍写"待实现、待独立验收"，与工作区已实现状态不一致（文档更新归主 Agent）。

#### H. L0/L1/L2/L3

- **L0 Runtime：BLOCKED（未执行）**。阻塞层：R3.0-006 用户授权未取得、008B 双重门（含
  R3.0-009 stage-3 机械增量）前置未满足、真实 modeling start 未启动；另受 F7 影响（真实 run 的
  freeze 快照仍无法经产品路径产生）。
- **L1 Modeling quality：BLOCKED（未执行）**。同一阻塞层；本轮无真实问题、参考答案、分组或模型
  证据，**不作任何语义质量声明**，不填四态逐题表。
- **L2 Repeatability：未执行**（依赖 L0/L1）。**L3：`not in scope`**。
- 外部依赖/授权：未执行 = L0/L1/L2；失败 = F7；已修复 = F1–F6；未授权 = 真实批次验收。

#### I. 未执行清单与原因

| 项 | 未执行原因 |
| --- | --- |
| L0 真实批次（R6/R7 的真实运行时面、M12 的真实 LLM 面） | 无用户授权、008B 双重门前置未满足、真实 modeling start 未启动；且 F7 使真实 run 无法产生 freeze 快照 |
| L1 逐题四态判定 | 依赖 L0；无真实问题/参考答案/分组/模型证据 |
| L2 重复性 | 依赖 L0/L1 |
| L3 产品化 | `not in scope` |
| R5/R8 的单题语义 miss、unknown 补猜判定 | 属 L1 语义判定，只有 validator 机械面证据 |

#### J. 清理与残余风险

- 本轮自建 run root/ledger（`workspaces/modeling-runs/r3011r2-*`）已全部删除，`/tmp/r2_probe*.py` 已删除；
  未遗留任何本轮 fixture。
- 残余风险：F7 使"Delivery host 触发冻结 → 只读批次验收"的真实闭环仍未打通（机械/Runner/CLI 各段
  已分别验证正确）；R4 的"不再盲测"标注未实现（机制替代，待主 Agent 裁决）；`pass`+layer、
  `revision` 非单调、`requirements-v3.0.md:202` 状态为记录级事项。F7 修复并复测 M8/M12 真实触发面后，
  方可排期 L0。

### Round 3 — 独立功能测试复测（2026-09-09，独立需求测试 agent，只覆盖变更面）

**总体结论**：机械/隔离 = **PASS**（Round 2 F7 **FIXED**、R4 "不再盲测"标注 **FIXED**、
`pass`+layer informational 闭合；本轮未发现新缺陷）；L0 Runtime = **BLOCKED**；L1 = **BLOCKED**；
L2 = 未执行；L3 = `not in scope`。本轮未启动真实 modeling start、未调用真实 LLM/外部 API、
未消耗 semantic start 授权，**没有任何语义质量结论**；未执行不计为通过。

**范围裁剪（按主 Agent 指令，明确声明）**：本轮只复测 Round 2 之后变更的面 —— F7 前台准入、
R4 非盲测标注、`pass` 层守卫，以及受影响门禁套件；未重跑 Round 1/2 的 F1–F6 全矩阵，
Round 1/2 的结论与证据原样保留。

#### A. 轮次与代码状态

| 项 | 记录 |
| --- | --- |
| 代码版本 | branch `main` @ `ec5c690` + 未提交工作区（相对 Round 2 再修改：`__main__.py`、`runner.py`、`competency_questions.py`、`acceptance.py` 及 011 测试）；本轮未修改任何产品代码、未 commit |
| profile/task | `r3-0-011-competency-question.yaml` + `r3-0-008b-staged-real.yaml`；门禁另跑 002/008B/009 wiring 与 R2.3/全量 |
| 授权 scope | 无真实用户授权；仅机械/fixture/隔离探针 |
| run/batch/session ID | run root 全部为本轮独占的 `workspaces/modeling-runs/r3011r3-<sha256[:10]>`（含一个 `-rec` 恢复模拟 root），用后即删；batch ID `cq-batch-0001` 等 |
| artifact digest | 前台冻结快照 digest `sha256:7e7b0b5a…17449`（K5/K6 一致）；exposure 证据 digest `sha256:169137fc…06225e`（K10/K11 一致） |
| cleanup owner | 本轮 run root、ledger 与 `/tmp` probe、handoff 全部由本轮删除（见 E） |

#### B. 已执行命令与结果

```bash
uv run --project backend python -m pytest -q modeling_team/tests/test_r3011_acceptance.py \
  modeling_team/tests/test_r3011_contracts.py modeling_team/tests/test_r3011_cq_lifecycle.py \
  modeling_team/tests/test_r3011_runner_wiring.py
# → 96 passed in 1.69s
uv run --project backend python -m pytest -q modeling_team/tests/test_r30002_runner_wiring.py \
  modeling_team/tests/test_r30008b_runner_wiring.py modeling_team/tests/test_r30009_runner_wiring.py
# → 49 passed in 1.11s
env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest -q modeling_team/tests
# → 1309 passed, 1 skipped, 318 subtests passed in 47.90s
cd backend && uv run pytest -q
# → 1006 passed, 36 skipped in 53.35s
```

四项计数与开发自述完全一致；全量建模与 backend 套件无回归。仓库侧已补上前台路径测试
（`test_r3011_runner_wiring.py::test_f7_foreground_path_freezes_the_pool`、
`test_f7_foreground_gate_rejects_unknown_cq_actions`），Round 2 指出的"无前台路径仓库测试"缺口已闭合。

#### C. 变更面复测结果

**F7 — `cq_freeze` 前台准入（FIXED）**：独立探针在 011 run 上经 `_handle_foreground_message`
（stdin 与 outer FIFO 共用的真实准入路径）发送 `{"action":"cq_freeze"}`：

- `cq_freeze` 已在 `_KNOWN_OUTER_ACTIONS`（`__main__.py:142`），且 `_CQ_OUTER_ACTIONS` 与
  known gate 的 CQ 子集完全一致（K1/K2）；
- 未知动作 `{"action":"cq_freeze_now"}` 仍被 known gate 拒为 `outer-input-rejected`，无快照（K4）；
  同 run 的合法 `cq_review` 行继续被接受（K3）；
- 前台 `cq_freeze` 行 → `{"type":"cq-frozen","freeze_id":"cq-batch-0001","snapshot_digest":"sha256:7e7b0b5a…", "public_question_ids":["cq-r3-pub"],"hidden_question_count":1,"phase":"frozen"}`（K5），
  `frozen/freeze-0001.json` 权限 `0o440` 且重载 digest 与 ack 一致（K6）；
- **真实链路闭合**：同一 run root 上 `cq-acceptance` exit 0（`full_pass=false`，K8）。
  Round 2 的 `cq_freeze_unreachable` 在真实前台路径上不再成立。

**R4 — 非盲测标注（FIXED，按计划 D 行偏差项）**：标签由 Runner 写的
`evidence/cq-exposure.jsonl` 推导（`competency_questions.py:753 read_exposure_evidence` /
`:819 blind_batch_label`），冻结快照 schema 不变（`r3-0-011-cq-freeze/v1` 顶层字段集精确、
无 exposure/blind 字段，K13）：

- 有曝光的批次（真实前台冻结 + CLI）：报告 `blind_status = {"blind_status":"non-blind-regression",
  "exposed_question_ids":["cq-r3-pub"],"exposure_evidence_digest":"sha256:169137fc…","exposure_record_count":2}`
  （K10）；`attribution.json` 带同一 label/ids/digest（K11）；CLI stdout 报告 `blind_status`（K9）；
  `batch-packet.json` 保持精确两字段盲测子输入合同，未携带标签副本（K12）；
- 无曝光池 → `blind`（exposed ids 空、record_count 与证据文件一致、digest 覆盖全部记录，L2）；
- **交集语义**：批外题的曝光不使本批次变非盲（CLI 端到端 L3、label 单元 L4/L5/L6）；
- 证据缺失/损坏：非 JSON 行 → exit 2 `cq_exposure_evidence line is not JSON`
  （`read_exposure_evidence` reason `cq_freeze_schema_mismatch`），绝不猜成 blind（L7）；
  文件缺失 → 空 provenance、`blind`、record_count 0（L9）；
- provenance 跨 freeze/恢复存活：`_cq_exposed` 不被 freeze 清空（L8）；把恢复的 Runner 重新挂到
  同一 run root 后 `_cq_merge_exposure_evidence`（`runner.py:5388`，freeze 门 `:5644` 调用）从证据重读
  曝光（L10），并且对已展示题再提案 hidden 在**草稿时刻**即被拒 `cq_hidden_exposed`（L11，比 freeze 更早）。

**informational 闭合 — `pass` 不得带 failure_layer**：`validate_acceptance_verdict` 对四个层
（`modeling-quality`/`platform-contract`/`collaboration/routing`/`runtime/infrastructure`）逐层拒绝
`pass`+layer（M1），`pass` + 空层仍接受（M2）；仓库测试 `test_r3011_acceptance.py:917` 覆盖。

#### D. Informational（本轮，不计缺陷）

- 全公开投影为零时，panorama 审核仍会写一条 `question_ids: []` 的曝光记录；标签仍为 `blind`，
  digest/record_count 如实记录（L1/L2）——不影响判定，仅记录。
- 证据文件缺失时 `exposure_evidence_digest` 是"零条记录"的 digest（`sha256:4f53cda1…`）而非 `null`；
  与 `build_batch_report` 未计算标签时的 `null` 缺省可区分，语义是"已核对过证据"（L9）。
- Round 2 其余 informational（`revision` 非单调、`requirements-v3.0.md:202` 状态未更新）保持不变。

#### E. 清理与残余风险

- 本轮自建 run root/ledger（`workspaces/modeling-runs/r3011r3-*`，含 `-rec`）、`/tmp/r3_probe_f7_r4.py`
  与 `/tmp/*-handoff.json` 已全部删除，无遗留。
- 残余风险：L0/L1 仍 BLOCKED（R3.0-006 用户授权、008B 双重门前置、真实 modeling start 未启动）。
  F1–F7 与 R4 标注均已闭合，机械/隔离面无已知 High/Critical；真实批次验收（语义质量）仍待授权后排期。

#### F. 判定汇总（§8）

- 机械/隔离：**PASS**（本轮变更面；Round 1/2 结论保留）。可重试路径：无；可直接排期 L0 前置。
- L0 Runtime：**BLOCKED**（授权 + 008B 双重门 + 真实 modeling start 未满足）。
- L1：**BLOCKED**（同上；无真实问题/参考答案/分组/模型证据，不作语义声明）。
- L2：未执行；L3：`not in scope`。外部依赖：未授权 = 真实批次验收；失败 = 无；未执行 = L0/L1/L2。
