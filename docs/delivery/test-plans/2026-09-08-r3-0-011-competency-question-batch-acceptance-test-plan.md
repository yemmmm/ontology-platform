# R3.0-011 能力问题驱动建模与批次级语义验收 — 共享测试计划

- 关联设计：[2026-09-08-r3-0-011-competency-question-batch-acceptance-design.md](../designs/2026-09-08-r3-0-011-competency-question-batch-acceptance-design.md)。
- 当前状态：计划评审 Round 2 专项复审 PASS；功能测试尚未执行。本轮不启动真实 modeling start，也不把 fixture/机械 PASS 当成语义质量 PASS。
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
| D1 | 需求、设计、计划互相引用；D1–D10、非目标、四态、四层归因、D5 延后 model binding 均写明 | `rg`/链接检查，人工逐项核对；无实现/运行完成措辞 |
| D2 | 008B stage 2 在切片前接收 CQ public projection；009/008A/006 交界不重复建设 | 需求与关联设计段落/路径核对 |
| D3 | 旧 R2.3 Source/Platform/Acceptance fresh 合同与新 v3 batch 合同分开 | 旧 profile/task/schema 快照与新 selector 对照 |
| D4 | 建议题量是建议而非硬门，用户审核不能由 Agent 推荐替代 | 合同字段和负例检查 |

## 3. 机械合同、选择器和成功边界（M）

| ID | 场景 | 预期 |
| --- | --- | --- |
| M1 | 011 参数为 true，加载 011 Profile + 008B staged real task | loader 接受：核心三角色各一、CQ role 各一、profile/task digest 一致；不启动 Agent |
| M2 | 旧 002 Profile/Task、旧 R2.3 formal Profile/Task 不带 011 参数 | 行为、role set、capability 广告和旧 schema 回归；不出现 CQ operation |
| M3 | role/package 合同、`ROLE_VALUES`、Profile extra role、task parameter 及通信边 | 缺 role/重复 role/未知 parameter/缺核心角色/非法边 typed reject；额外 CQ 不被“固定三角色”误拒 |
| M4 | role source manifest | CQ 与 Modeling 获得同一四个业务输入；生产角色未获得 tester-only、参考答案、CQ private；Acceptance 只获得冻结的引用原文副本；Examiner 未获得 source directory 或原文 |
| M5 | `cq_publish_question_draft` 工具广告和 dispatch | 仅 011 CQ endpoint 广告；schema、owner、run ID、content digest、revision 错误只拒当前草稿；CQ 无 platform tool，生产角色无 CQ private tool |
| M6 | public projection | 全景审核后只将获批 public 题/答案投影给切片生产角色；投影不含 hidden 题干、答案、ID 提示、CQ 私聊或未审核记录 |
| M7 | review action | `cq_interview`/`cq_review` 仅接受 outer FIFO 的严格字段，直接唤醒 CQ；批量/逐题批准、修改、删除、补题皆可；revision/digest/owner 错误经CQ专用分支拒绝，不经 Coordinator；验证CLI/FIFO仍存活、run/session ID不变、下一条合法审核成功，旧receive_outer致命边界不被广泛吞掉 |
| M8 | 分组时点 | 全景 hidden 预留、slice 只读 public projection、slice 审核后最终 freeze；曾展示给任一生产角色的题在负例中不能转 hidden |
| M9 | freeze snapshot | 稳定题 ID、scope、题干、答案要点、依据、unknown、visibility、review version/binding、材料 digest、snapshot digest 闭合；旧版本追加保留，不能原地覆盖 |
| M10 | 题量边界 | 低于/高于建议范围、切片数量变化、重复候选只给可修复反馈或按用户批准继续；不因固定题数、切片数、Agent 数硬拒 |
| M11 | D5 late model binding | 冻结阶段没有虚构 workspace/model state；验收启动时绑定每个显式 Ontology 的授权和状态，缺状态/越权/漂移拒 batch；不全项目扫 |
| M12 | 独立验收启动/终态 | `cq-acceptance` 读取原 run 配置，绑定freeze和稳定交付模型；pending checklist不阻止启动，生产未静默/未决写入不能开始；Evaluator输出host-only报告，Delivery只交脱敏摘要，不产生终态循环；CQ跨全景/切片审核复用同session，frozen不提前终态，production handoff后接收cq_handoff_complete并恰好一次report_task_result；全roster可settle，不等Acceptance才结束CQ；提前terminal只拒当前调用，不入账且同session可继续 |
| M13 | v3 packet与角色提示 | Platform为单批次session、无Source；随后独立Acceptance session只读冻结输入并交报告；实际工具广告和提示匹配v3，不要求旧source report，不允许Acceptance启动/继续/修复run |
| M14 | 参考答案依据 | Acceptance收到冻结引用原文/访谈bytes与digest，能识别原文与答案冲突；Examiner看不到该包；纯待复核允许failure_layer为空，不能误算modeling-quality |
| M15 | 验收期间模型变化 | 前后状态重验发现变化时不沿用旧PASS，保留旧batch并标未完成；不新增锁/状态管理框架 |
| M16 | 空隐藏集/切片无有效隐藏题 | 可以继续建模，但保留验收覆盖缺口；不以空集合或删题后的分母产生整批/全场景PASS |

## 4. 信息隔离和泄漏负例（I）

| ID | 检查面 | 预期失败/证据 |
| --- | --- | --- |
| I1 | `role_sources` | Modeling/Coordinator/Protocol 尝试读取 CQ private、hidden freeze、参考答案或 tester-only 路径均不可读；CQ 可继续读获准业务材料 |
| I2 | artifact bind | 生产角色 namespace 只挂 public projection；CQ private/reviews 和 hidden packet 不存在于其路径；Examiner 不见 answer/frozen reference，Acceptance 不见生产私聊 |
| I3 | team messages/log/history | hidden question/answer/答案提示/未过滤 review 文本不得进入 Coordinator/Modeling/Protocol delivery、team transport event log、role history、共享 evidence 文本；只保留 IDs/digest/status/path |
| I4 | capability endpoint | 011 selector 广告和 role-token 绑定准确；CQ 不能调用 platform/read proxy，Modeling 不能请求 hidden packet，Examiner 只能只读语义 + report sink，Acceptance 不能写平台或启动 Agent |
| I5 | repeated exposure | 模拟先 public 后改 hidden、CQ 向 Coordinator 误发 hidden、共享目录放置 hidden 文件；Runner 保留泄漏证据、把题永久 public 或 reject，不能继续把它计 blind |
| I6 | authorized multi-Ontology | hidden packet 只含获准 Ontology 显式列表；未授权 Ontology、跨 project IRI 和不存在/无权语义都不通过错误侧信道泄漏 |

## 5. 审核、恢复和报告机械用例（R）

| ID | 场景 | 预期 |
| --- | --- | --- |
| R1 | 审核等待/暂停、用户补题或修改一题 | run 可恢复；只重做受影响 panorama/slice 阶段，不消耗 semantic start，不重置其他批准；暂停审核不触发CQ任务失败/cleanup，恢复后同CQ session继续 |
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

在获用户授权且 008B/006 前置完成后执行一次真实批次：只启动一个 Platform Examiner hidden batch，确认 `source-examiner` 从未启动；Runner/Acceptance 记录固定顺序、每题 report、tool/read-only scope、已执行/未执行和终态。L0 只回答“运行合同是否存活、证据是否完整”，不判业务答案质量。

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
| plan review | Round 1 REVISE：H1外层输入致命边界、H2 CQ生命周期均accepted-high并已修订；Round 2 专项复审 PASS |
| implementation | 待实现；本轮未修改产品代码 |
| independent test | 待执行；本轮未启动真实 modeling start |
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
