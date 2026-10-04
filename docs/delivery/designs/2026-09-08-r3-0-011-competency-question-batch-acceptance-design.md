# R3.0-011 能力问题驱动建模与批次级语义验收 — 交付设计

- 状态：细化完成；Round 1 两项 High、Round 3 两项 High 修订后分别经专项复审（Round 2 PASS；Round 4 见 §8）；2026-09-09 实现完成，独立功能测试 Round 1–3 后机械/隔离 PASS（Round 1 六项、Round 2 F7+R4 标注偏差均修复复验；记录见共享测试计划），真实 L0/L1 批次验收待 R3.0-006 授权与 008B 双重门。
- 适用需求：`docs/requirements/requirements-v3.0.md` 的 R3.0-011；关联 R3.0-002、R3.0-006、R3.0-008B、R3.0-009。
- 本轮边界：只冻结功能合同和实现交接，不启动 semantic modeling start，不生产真实问题/答案，不宣称模型质量或运行通过。

## 1. 目标、边界和复用

R3.0-011 在 R3.0-008B 的真实任务中插入能力问题阶段：先形成场景级全景问题，再依据获批逻辑切片形成切片问题；用户审核后，冻结公开建模题和隐藏验收题。公开题指导建模，隐藏题验证模型是否能回答未展示问题。v3 的隐藏验收只验证平台语义支撑，数据库实际 SQL 和结果比对仍由 R3.0-006 负责。

复用现有 `modeling_team` 的 Profile/roster、Task、Runner、role-scoped `role_sources`、sandbox bind、Team Transport、Runner-private capability endpoint、只读平台代理和 examiner report sink。当前 [r3-0-008b-staged-real.yaml](../../../modeling_team/tasks/r3-0-008b-staged-real.yaml) 仍只有 Coordinator/Modeling/Protocol 三角色；[r3-0-002-modeling-team.yaml](../../../modeling_team/profiles/r3-0-002-modeling-team.yaml) 也只有这三角色。现有 `acceptance.py` 的 Acceptance/Source Examiner/Platform Examiner 是 R2.3 逐题 fresh 合同，不能直接声称已支持本需求。

本需求不新增平台资源、API、数据库表、通用题库/权限系统、动态 Agent 创建、自动问题评分、固定题数硬门、自动恢复框架或 UI。旧 R2.3 Task/Profile/Acceptance 合同显式选择时保持原行为。

## 2. 决策记录

| 决策 | 冻结合同 | 推荐把握与依据 |
| --- | --- | --- |
| D1 审核 | 用户可批量或逐题批准、修改、删除、补题；Delivery 记录决定，Agent 不能代批。决定绑定题目内容版本；等待审核可恢复 | ≥95%；直接落实需求中的用户审核和失败恢复边界 |
| D2 分组时点 | 全景审核时由 CQ/用户/Delivery 预留隐藏题；切片分析只收到获批公开投影；切片题审核后冻结最终分组。题/答案一旦展示给任何生产角色，永久按公开处理 | ≥90%；消除“先用全景题切片、后隐藏”造成的泄漏 |
| D3 隔离 | CQ、用户/Delivery、Platform Examiner、Acceptance 各按职责取私有材料；生产 Coordinator/Modeling/Protocol 只取公开投影。隔离覆盖 `role_sources`、artifact、消息/日志/历史、能力端点 | ≥95%；单靠 prompt 无法防止间接泄漏 |
| D4 题目记录 | 每题保存稳定 ID、全景/切片 scope、题干、答案要点、材料/访谈依据、unknown、public/hidden、审核内容版本和绑定。采用本地 run artifact，不建通用题库版本系统 | ≥90%；满足逐题裁决、局部修订和追溯最小需要 |
| D5 验收绑定 | 冻结题池时只绑定题目/材料/审核版本；模型交付后启动验收批次时，Runner 再绑定获准 Ontology 集合及每个 Ontology 的授权状态/工作区状态 | ≥95%；避免引用冻结时尚不存在的模型版本，沿用 006 授权边界 |
| D6 判定 | Acceptance 按必要业务要点和证据判定，不逐字比较；有依据的 unknown 可通过，补猜不能通过 | ≥90%；源忠实度优先于文字匹配 |
| D7 待复核 | 题目/答案冲突、歧义或材料不支持时保留题和缺口，状态为 `question-answer-review`；不能静默删题或缩小分母绿灯 | ≥95%；不把出题缺陷归因模型，也不掩盖覆盖缺口 |
| D8 重试 | 只读报告/查询修复优先继续同一批次会话；丢失上下文需新 session/batch 并留证，不拼接为单会话 PASS。被隐藏题泄露后可做回归，但必须标明不再盲测 | ≥90%；保留独立性且不以次数硬杀可恢复流程 |
| D9 兼容 | 新 v3 任务显式选择器；新增 CQ role/package 和独立 011 Profile，保留 002 Profile。复用现有 roster/加载/隔离机制，不把 CQ 固定角色变成全平台硬门 | ≥90%；当前 `load_profile(multi_slice=True)` 已按已知 role 含核心角色接受额外角色，缺的是 CQ role 注册和 011 wiring |
| D10 层级 | 文档、机械/L0、L1 语义质量、L2 重复性、L3 产品化分别取证；后层不作前层前置，真实联合验收仍挂 008B 第二段及 006 用户授权 | ≥95%；遵循仓库 L0-L3 和 semantic start 授权规则 |

上述推荐没有待用户裁决项。用户审批权、未来真实问题/答案/分组和真实 modeling start 授权不由这些推荐替代。

高风险假设（最多三项，均需实现/独立测试验证）：

1. 现有 outer FIFO/Runner delivery 可以增加按 `competency-question` role 定向的严格 action，而不引入新的 UI/API；若现有输入循环不能安全识别该 role，保留同一 Runner-owned local channel 并在 `__main__.py` 增加窄分派。
2. 现有 `load_profile(multi_slice=True)` 的额外已知 role、按 role 的 source staging 和 Codex 定向 bind 足以承载 CQ；只需注册 role、增加独立 Profile/Task selector 和 capability wiring，不把 CQ 变成所有 Team 的硬门。
3. 现有 Platform Examiner read proxy/report sink 可以承载一个连续 hidden batch；若旧 `Acceptance/ExaminerRolePacket` 的 source+platform 逐题输入在实现中无法复用，则在 `acceptance_runtime.py` 增加 v3 batch 分支，旧 R2.3 分支保持不变。

## 3. 角色和阶段合同

### 3.1 显式选择、加载和既有任务

实现阶段为 R3 task 增加一个封闭的 `parameters.competency_question_acceptance: true`（显式、布尔、任务级选择器），并要求同时选择现有 `multi_slice_workflow`、`staged_modeling_decisions`。真实任务入口固定为 `modeling_team/tasks/r3-0-008b-staged-real.yaml`；未选择该参数时，R3.0-002 和既有 R2.3 路径不加载 CQ 合同。

新增并绑定：

- `modeling_team/agent-packages/competency-question/package.yaml` 与 `instructions.md`，role 值为 `competency-question`；无平台读写权限，草稿只经角色绑定的 Runner capability 保存；可读取与 Modeling 相同的获准业务输入。提示只允许生成/维护问题及依据，不允许平台读写、Ontology 候选或向生产角色发送私有题目。
- `modeling_team/profiles/r3-0-011-competency-question.yaml`：复用 Coordinator、Modeling、Protocol 核心 Agent，加一个 `competency-question` Agent；profile 的通信/工具广告由任务选择器决定。CQ 不通过 Coordinator 中心传递私有审核消息。
- `modeling_team/references/r3-0-011-competency-question-contract.json`：只描述 schema、阶段、状态和可见性，不含当前业务答案。
- `modeling_team/tasks/r3-0-008b-staged-real.yaml`：显式选择器、CQ 可见的四个 R3.0-001 业务输入和 011 contract；生产角色仍按角色白名单获取输入，tester-only/参考真值不进入 `role_sources`。

加载链路必须闭合为：Task 参数 → `load_multi_slice_team_configuration`/`load_profile(multi_slice=True)` → `ROLE_VALUES` 注册和 role 唯一性校验 → role package/profile digest → Runner role map → per-role source/artifact bind → `_role_capability_operations`/`RunnerCapabilityEndpoint` → `runner-capabilities.json` 广告。既有三角色任务的 profile、通信边和 capability 集合保持字节级兼容；不能把“有 CQ”写成所有 multi-slice run 的合法性前置。

当前缺口以源码为准：`contracts.py` 的 `ROLE_VALUES`/Task parameter 集没有 CQ role/selector；`r3-0-008b-staged-real.yaml` 的 `role_sources` 没有 CQ/public projection；`r3-0-002-modeling-team.yaml` 没有 CQ（也没有 Acceptance）；`runner.py` outer question 目前只观察 Modeling→Coordinator；`acceptance.py`/`acceptance_runtime.py` 的旧输入是 Source+Platform Examiner 逐题 ticket。下表是实现交接缺口，不是本轮已实现事实。

### 3.2 CQ 生成和用户审核

CQ Agent 与 Modeling 共享获准业务材料，并可在全流程持续接收新的用户访谈输入；共享材料本身不是泄漏。CQ 的私有对话、未审核题、隐藏题、答案和审核讨论只进入 CQ 私有会话/目录，不能通过 Coordinator 转发给生产团队。用户/Delivery 直接把访谈或审核输入送到 CQ 的 Runner-owned direct channel。

最小本地交付通道：Runner 在 `--enable-outer-input-fifo` 已有的 outer 控制面上增加 `cq_interview` 和 `cq_review` 两个严格 action。CQ 以 Runner-private `cq_publish_question_draft` capability 提交不可变草稿；Runner 产生 `cq-review-request` 事件并只把 `review_id`、文件相对路径、digest、状态和可读入口交给 Delivery。Delivery 读取该 review snapshot 给用户审核；用户以 `cq_review`（`review_id`、题目 ID/当前 revision、`approve|modify|delete|supplement`、修改内容或补题）回传。Runner 校验 owner、revision、schema 和 digest，把决定写入 CQ review artifact，再以直接 `user/outer → competency-question` delivery 唤醒 CQ。审核内容不经 `team-transport`，不进入 Coordinator 的消息、日志或历史。

CQ/Runner 对每一题保留追加式 draft/review 版本。审核等待、一次拒绝、字段错误或补题只阻断当前问题阶段并返回可操作错误；修复后继续同一 run。生产方只能收到 Runner 根据用户已批准结果生成的公开投影。

CQ 外层输入必须在现有 fatal 边界之前完成窄分派：`__main__.py` 的
`_handle_foreground_message` 对 `cq_interview`/`cq_review` 调用 CQ 专用的准入/处理分支；
Runner 在该分支对字段、owner、审核 revision/digest 和阶段冲突返回类型化 rejection（对象、阶段、
reason code、可重试说明），不把这些预期输入错误抛成 `TeamConfigurationError` 进入现有
`receive_outer` 的致命边界。拒绝不改变原审核版本，事件与错误不得带隐藏题干/答案，CLI/FIFO
继续读取下一条输入。同一条 CQ input 经 stdin 或 FIFO 必须采用同一规则；不广泛捕获旧路径
`TeamConfigurationError`，不把持久化、Runtime 或不可控故障伪装成用户输入拒绝。其他运行失败
仍按仓库 T0 和已有安全恢复边界处理，不扩大本需求的错误吞掉范围。

CQ 生命周期以现有 run artifact/任务提示维护以下阶段，不建设独立编排框架：
`panorama-draft → panorama-review → awaiting-slices → slice-draft → slice-review → frozen`。
拒绝/修改只回到相关 draft/review；新的获准访谈输入或冻结修订仍送到同一 CQ session。
`frozen` 表示当前题池已交付，不等于 CQ 已结束；CQ 保持静默可继续状态，直至 Delivery 确认生产
handoff 就绪、无待处理 CQ 审核或补题且该题池版本是本次交付基线，才发出 `cq_handoff_complete`。
生产 handoff 就绪只检查生产角色的交付与静默，不以 CQ 或全 roster 已 terminal 为前置。
该 host-only action 只带 freeze ID/digest 和交付绑定，按同一 CQ 可恢复准入分支校验。
CQ 此时且仅此时调用一次既有 `report_task_result`，终态内容只含交付 ID/digest/状态，不含隐藏题。
Runner 在 CQ 正确终态前不允许整体 settle；其余角色正常交付后，现有全 roster settlement 可结束，
不要求 CQ 等待独立 Acceptance 的结论。没有就绪的 production handoff 不能提前关闭 CQ。011 模式的 CQ 若提前调用 terminal 工具，
角色绑定的 Runner/transport 准入返回当前阶段与继续动作，不登记不可撤销 terminal，也不杀 run；
修改点必须同时覆盖工具广告、结果准入与CQ提示，不能只靠提示劝阻。

011 的 CQ task prompt 必须使用以上阶段提示，替换通用“完成整个建模目标并立即 report_task_result”
文案；中间轮的 turn 结束或等待用户不是 task terminal。Runner 把显式等待用户审核记为可恢复等待，
不得因用户审核耗时把 CQ 视为失败或清理会话；复用已有等待/继续机制，修订只影响当前题阶段。
现有 run 级 T3 防御与该合同直接冲突，必须一并处理：`runner.py:5683` 每 tick 调用
`_check_run_fallback_timeout`（`runner.py:4913` 起），`runner.py:1843` 起无条件启动 5400 秒默认
累计 active 时钟，超时即 `collaboration/routing:run-fallback-timeout` terminal latch 并清理 run；
其排除项只有 formal issue-pending，CQ 审核等待不在内。实现必须把“已发出 `cq-review-request`/
handoff 请求、等待用户或 Delivery 回应”的窗口按同类记账纳入该超时排除，窗口自请求发出起至回应
或 CQ 恢复为止；不删除、不放宽 T3 对真实停滞的保护，等待窗口不得被写成 `collaboration/routing`
失败证据。
最终 handoff 后新提出的修订另记后续交付，不对已 terminal 的 CQ 会话悄悄追加任务，也不自动新开
semantic start。异常退出保留未完成阶段和证据，不伪造最终 terminal report。

### 3.3 全景、切片和冻结

阶段顺序为：

1. CQ 依据获准业务材料和已有用户输入生成全景题、答案要点、依据和 unknown；用户逐题/批量审核。
2. 全景审核时由 CQ/用户/Delivery 预留 hidden 候选。Runner 生成只含已批准公开题/答案的 public projection，切片分析从该投影开始；CQ 可继续取得新的用户访谈输入，但生产方不能读 CQ 私有对话。
3. Coordinator/Modeling 依据公开投影完成获批逻辑切片；CQ 只为获批切片生成切片题并再次送用户审核。
4. 最终分组时合并全景和切片题，冻结 public/hidden；任何曾展示给 Coordinator、Modeling、Protocol 或其他模型生产角色的题/答案永久转为 public，不能再计 hidden。
5. 冻结后题池和参考答案不可原地改写。用户修订产生新题目版本并记录影响题/切片；旧版本、旧回答和旧裁决保留。修改前已用于生产的题只能用于标明的回归，不再是 blind evidence。

既有 R3.0-002 scenario map 合同要求 Coordinator 维护含题干文本的 `cross_slice_competency_questions`
节（`scenario_map.py:284` 逐项校验 `question` 非空），该合同属于 `r3-0-008b-staged-real.yaml` 生产
角色 `role_sources` 和 `scenario-map-six-sections-maintained` 终态证据。011 模式下该节只能引用 CQ
题池公开投影中的题（`question_id`/题干与公开投影一致），或显式置空并记录跨切片覆盖缺口；生产角色
不得从原始材料自行撰写新跨切片题干，避免形成绕过“展示即永久公开”规则、与隐藏全景题平行的第二套
已展示题集。该约束进入 011 的角色提示与机械校验；对应泄漏负例由测试计划覆盖。

冻结快照（建议 schema `r3-0-011-cq-freeze/v1`）每题至少包含：

```json
{
  "question_id": "cq-…",
  "scope": {"kind": "panorama|slice", "slice_ids": ["S3"]},
  "question": "…",
  "answer_points": ["…"],
  "evidence_refs": [{"source": "…", "locator": "…"}],
  "unknown": ["…"],
  "visibility": "public|hidden",
  "review_content_version": 3,
  "review_binding": {"review_id": "…", "decision_digest": "…"}
}
```

快照还保存 batch ID、材料 digest、全景/切片集合、排序和 snapshot digest。题量只用于建议覆盖范围（全景 5–8、每切片 3–6、hidden 总量通常 6–10），不得成为 Runner 合法性或 run 失败硬门。快照不绑定模型 workspace；D5 的 `model_binding` 在验收启动时追加到新 acceptance batch，不覆盖题池快照。011 题池只保存在 run artifact，不登记为平台资源；`modeling-batch-item-contract.json` 的 `competency_question_ids` 保持可选并留空，不把题池 ID 同步进平台 modeling batch。

### 3.4 输入隔离和能力端点

隔离必须同时覆盖以下面：

| 面 | CQ/Delivery 可见 | Modeling/Coordinator/Protocol 可见 | Examiner/Acceptance 可见 |
| --- | --- | --- | --- |
| `role_sources` | 四个业务输入、011 contract、CQ 自有合同 | 各自既有获准业务输入及已批准 `public-projection`，不扩大 Protocol/Coordinator 原有业务文件权限；无 CQ 私有路径 | Platform Examiner 不读源材料；Acceptance 只读冻结答案及其引用的获批原文副本，不挂载仓库/源目录 |
| artifacts | CQ drafts/reviews/private interview；Runner/Delivery 可读 | 只读 public projection、既有 008B/009 产物 | Examiner 只读 hidden batch packet + model binding；Acceptance 只读 freeze + reports |
| messages/logs/history | 用户与 CQ 的 direct channel | 不含 hidden 文本/答案提示；只能收到 public projection | 不含建模讨论；Platform Examiner 不读答案；Acceptance 不读 CQ 私有对话 |
| capability endpoints | `cq_publish_question_draft`、审核状态查询（无 platform） | 既有角色能力；无 hidden packet | Platform read proxy + report sink；Acceptance 只读 verdict/报告输入 |

Run root 下建议分目录：`competency-questions/private/`、`competency-questions/reviews/`、`competency-questions/public/`、`competency-questions/frozen/`、`acceptance-v3/hidden-batch/`、`acceptance-v3/reports/`。private、reviews 和 hidden packet 只由 host/对应角色定向 bind；生产角色只得到 public 目录的只读投影。共享 `evidence` 可记录 ID、digest、状态和路径，但不能写入 hidden 题干、答案或 CQ 私有对话文本。不要用通用 ACL/题库服务替代这些既有 sandbox、role source 和 Runner bind。

public projection 的中段交付复用既有 per-role 只读目录 bind 模式（同 scenario-map 目录）：run 启动即
把 `competency-questions/public/` 只读 bind 进生产角色命名空间，Runner 随批准把投影文件追加写入该
目录，运行中命名空间可见；不通过 team-transport 消息或 Coordinator 转发投影内容。

## 4. v3 隐藏批次验收

### 4.0 启动、输入和结果交接

011 Profile 只包含三个生产角色和 CQ；独立 Acceptance 不加入该生产 roster。实现阶段在已有
`modeling_team/__main__.py` 增加窄命令 `cq-acceptance`，由 Delivery 调用，输入为 `--run-root`、
`--freeze-id` 和 `--model-handoff`。命令读取原 run 的 Task/配置快照并要求已选择
`competency_question_acceptance: true`，不能借命令名把旧 R2.3 run 切换为新验收合同。
此命令及下述 batch packet 是待实现增量，不是现有 CLI 已支持的能力。

启动条件是生产交付就绪，而不是整个 run 已 terminal：Protocol 已交付确定的 dry-run/apply、
readback、validation/reasoning 证据和每个 Ontology 的状态，生产角色静默且无未决写入。
Delivery 根据既有交付回执、在途操作与模型状态检查发起验收；复用现有状态重验/只读代理，不新建锁或
跨机器协调框架。008B 联合验收 checklist 可保留 pending，不能要求 checklist 已 PASS 才启动本命令。
模型状态在批次前后重验，若漂移则保留该批证据并标记未完成，不能对变化后的模型沿用旧 PASS。

命令经 `acceptance_runtime.py` 的显式 v3 分派复用现有 child runtime 创建一次 Platform Examiner
会话，使用版本化 batch packet（有序 `questions[]`、`model_states[]`、授权 scope、只读工具、
report schema、freeze/batch 绑定）；它完成或不能继续时保留逐题报告。随后通过同一既有 child
runtime 默认创建一个独立 Acceptance evaluator 会话。完整 Judge 首回合超过原生输入上限时，
在同一 attempt 按冻结顺序连续贪心分组，复用完整本题判定 packet 与独立 native child/report sink；
所有组绑定同一 freeze/model，不传前组裁决或旧 attempt 答案。宿主聚合全部题裁决，分母不变；
逐组披露 packet digest、输入长度、实际会话结果与 teardown，不称单会话完整证据。
完整单题仍超限记录逐题 `judge-input-too-large` 并跳过该题，继续其他合格题；
原分母不变，不裁剪证据，未创建 Judge 不记为 child 清理失败；未超限维持单会话形状。后者只使用冻结判定输入和 report sink，不持有
平台写、Team transport、创建/继续生产 run 或子 Agent 的能力。两种 packet、提示和报告都使用显式
v3 版本，不修改旧 `ExaminerRolePacket/v1` 的 source/platform/acceptance 字段合同；旧角色提示中的
逐题 fresh/Source report 要求在 v3 package 输入分派处换成 batch 合同，不能只修改调用参数。

Acceptance 的依据包必须包含题目引用的获批资料原文或访谈记录副本、locator、内容 digest 和
审核版本，不能只有无法读取的路径。资料副本从 CQ/Modeling 的获准材料及用户记录中取得，不能
添加 tester-only 真值；Delivery 在冻结时保存这些 bytes 与引用绑定，验收时只读交付给 Acceptance。
若片段不足以确定答案有效性，Acceptance 标记待复核并由用户处理，不补猜。Platform Examiner
始终不接收该依据包或参考答案。

结果写入 host-only `acceptance-v3/reports/<batch_id>/`，包含原 run ID、freeze digest、模型绑定、
逐题报告、四态裁决、覆盖和清理记录。Acceptance 只产出判定，不修改生产 run 或既有证据。
Delivery 在原 run 的 008B 联合验收记录中交接不含隐藏题干/答案的状态摘要与不透明报告 ID；
Coordinator 只据此关闭已有交付记录，不能读私有报告路径。若需修模，由 Delivery 按原授权和
隐藏信息边界另行交接；不是 Acceptance 自动续跑。只读验收命令不消费 fresh semantic start，
重新开始语义建模仍按 006 授权记录。

### 4.1 Platform Examiner

正式验收由一个独立的 Platform Examiner 子会话承担一个 hidden batch；复用已有 `platform-examiner` package、read-only semantic proxy 和 report sink 的隔离机制，但使用 v3 batch packet，不启动 Source Examiner。一个 batch 内按冻结 hidden 列表顺序逐题回答，可复用前题查询上下文；不读取答案、材料源目录、CQ 讨论、建模消息或历史。

Runner 在启动 batch 时从冻结题池和已交付模型状态生成不可变 packet，显式列出每个获准 Ontology 的 `project_id`、`ontology_id`、workspace/graph 状态、授权只读工具和题目 ID。多 Ontology 只能使用这份授权列表，禁止 Examiner 按 project 全量扫描。模型状态在这一刻绑定；状态缺失、授权不一致或状态漂移返回平台/运行时未完成。

Examiner 对每题返回并由 Runner 保存：题目 ID/version、自然语言回答、所用 semantic resource/relation/rule/value/mapping evidence、显式 unknown、`completed|unanswered|runtime-incomplete` 状态、failure layer/reason（如有）。单题召回失败不停止后续题；只有只读代理/运行时不可继续时才停止，并明确已执行和未执行题。Platform Examiner 不写平台、不修模型、不创建新 modeling start。

### 4.2 Acceptance 判定

Acceptance 是独立于 CQ 生成和模型生产的只读判定者；持有冻结答案要点、材料/访谈依据、审核版本、hidden batch packet 和 Examiner reports，不创建、继续或修复被验收的生产 run。它按题逐一对照必要业务要点和证据：

| 题目状态 | 含义 |
| --- | --- |
| `pass` | 必要业务要点由平台语义及证据支撑；参考答案中有依据的 unknown 被正确保留可通过；不要求逐字一致 |
| `model-recall-insufficient` | 题目/答案本身有效，但语义资源、关系、规则、值或映射链不足/错误；覆盖为 modeling-quality |
| `question-answer-review` | 题目/答案与获批材料冲突、关键歧义、依据不足或分组/修订影响未决；保留原题和覆盖缺口，不直接删题绿灯 |
| `platform-runtime-incomplete` | 平台/代理/运行时未完成，或题目未执行；已执行与未执行分开记录，不能按未执行当失败的模型质量 |

每题可填 `failure_layer ∈ {modeling-quality, platform-contract, collaboration/routing, runtime/infrastructure}`，仅在实际运行或模型失败有证据时填写；纯题目/答案待复核允许为空，并保留冲突依据，不能强行归为模型失败。`question-answer-review` 是题目状态，不是第五个 failure layer；平台原因不能推出模型质量。批次汇总分全景和各切片列出四态计数、覆盖缺口、已执行/未执行和 session/batch identity。完整 PASS 要求所有本批应验收题都有有效裁决且无待复核、未执行或不满足项；题量建议外的用户批准集合仍按实际列表驱动。某切片没有有效隐藏题，或隐藏集为空时，建模仍可继续，但须显式保留对应验收覆盖缺口，不能用空集合判整批或全场景 PASS。

涉及数据库实际结果的问题只在 006 SQL 链路中执行并比对；011 的 CQ Acceptance 只能证明语义上下文能导出所需概念、关系、规则和值/映射证据。RDF 不复制业务行仍按 006/008B 既有边界验收。

## 5. 失败恢复、兼容与清理

- 缺字段、旧 revision、digest 不匹配、不可达路径、隐藏内容误入 public projection、未授权 Ontology 或能力未广告：拒绝对应操作并返回对象/阶段/reason code；不杀死整个 run，修复后同阶段重试。
- 用户等待/修改/删除/补题：保留历史，局部回到受影响的全景或切片阶段；不以次数/题数、Agent 数量或固定会话数失败。
- CQ→生产的私有消息一旦错误展示：保留泄漏证据，受影响题标为 public；可继续建模并做标注为非盲测的回归，不能把后续成功冒充原始 blind PASS。缺失上下文的新 session/batch 另记，不拼批次。
- 只读重试不消耗 semantic starts；fresh modeling start 仍需用户授权。验收者不得通过工具启动或修复生产 run。
- 清理必须由 Delivery/Runner 负责：停止 CQ、Platform Examiner、Acceptance 子进程和 transport/capability socket；删除 owner 可证明的 private temp、packet staging 和测试 scope；保留冻结快照、历史 review、reports、failure/recovery/cleanup evidence。未知写入或 owner 不明时先保留并报告，不能盲删。

R2.3 继续使用现有 `r2-3-005`/`r2-3-003` formal profiles、Source Examiner、Platform Examiner、Acceptance ticket、逐题 fresh 会话和旧 failure enum；新参数不默认注入，旧 `acceptance.py` validator/role operation 集合不改语义。v3 分支应在 Runner/acceptance runtime 选择器处明确分派，不能只换 prompt 或把旧 `validate_ticket` 当成新合同。

边界错误采用稳定、可定位的窄 reason code（示例）：`cq_selector_incompatible`（选择器依赖缺失）、`cq_review_stale`（审核 revision/digest 过期）、`cq_public_projection_missing`（切片前公开投影缺失）、`cq_hidden_exposed`（已展示题尝试转 hidden）、`cq_freeze_schema_mismatch`（冻结快照字段/引用不闭合）、`cq_model_binding_missing`（验收启动未绑定模型状态）、`cq_batch_scope_unauthorized`（Ontologies 不在获准列表）、`cq_batch_context_lost`（同一会话上下文丢失）。这些错误只阻止当前操作并返回修复对象；平台/运行时已无法继续时才产生 `platform-runtime-incomplete`，并记录四层 failure layer，不把可恢复错误变成永久 run 失败。

## 6. 实现交接与文件范围

以下是实现阶段的最小落点，当前细化不创建这些代码文件：

| 目的 | 预期落点 |
| --- | --- |
| role 注册、011 参数、profile/task 选择和兼容校验 | `modeling_team/contracts.py`、`modeling_team/profiles/r3-0-011-competency-question.yaml`、`modeling_team/tasks/r3-0-008b-staged-real.yaml` |
| CQ package、合同和提示 | `modeling_team/agent-packages/competency-question/{package.yaml,instructions.md}`、`modeling_team/references/r3-0-011-competency-question-contract.json` |
| CQ draft/review/freeze schema、版本和 reason code | `modeling_team/competency_questions.py`（纯机械校验/摘要，不做语义评分） |
| 用户直达审核/访谈、public projection、freeze 和 D5 model binding | `modeling_team/runner.py`、`modeling_team/__main__.py`（复用 outer FIFO，不经 Coordinator） |
| role source、artifact bind、消息/日志/历史和工具 surface 证据 | `modeling_team/runtimes/codex.py`、`modeling_team/capability_mcp.py`、`modeling_team/acceptance.py` |
| v3 单 batch Platform Examiner 与 Acceptance 判定交接 | `modeling_team/__main__.py` 的 `cq-acceptance`、`modeling_team/acceptance_runtime.py`、`modeling_team/standalone_platform_examiner.py`、既有 `platform-examiner`/`acceptance` package 的版本化输入与提示；新增 v3 branch，保留旧 source/platform fresh 分支 |
| 共享测试 | 本设计对应的 `docs/delivery/test-plans/2026-09-08-r3-0-011-competency-question-batch-acceptance-test-plan.md` |

校验链必须至少包含：contract loader/schema → revision/visibility/freeze validator → role-source/public projection visibility probe → capability operation/role binding → examiner packet/report schema → acceptance four-state/failure-layer validator → task/profile advertised tools。校验只判断可观察结构、来源、授权范围、交接和执行状态，不判断业务答案好坏；语义质量留给独立 Acceptance 和真实 L1。

## 7. 验收边界

平台/流程实现完成需有机械合同、isolated role evidence、旧 R2.3 回归、cleanup 和 L0 Runtime 证据；这不等于真实语义 PASS。真实验收的启动前置沿用 `r3-0-008b-staged-real.yaml` 双重门（含其所列 R3.0-009 stage-3 机械增量）及 006 用户授权。真实 L1 至少证明：用户批准的全景/切片题池、public/hidden 隔离、一个 Platform Examiner 顺序完成 hidden batch、Acceptance 四态逐题判定、unknown 保留、multi-Ontology 授权 scope、至少一个语义代表问题；SQL 结果/RDF 无业务行由 006/008B 独立证据承担。L2 只能在 fresh batch/session 的重复性证据后判定，L3 产品化不作为本需求前置。

本设计不记录实现通过、真实建模通过、服务健康或用户审批事实；这些由共享测试计划和后续交付记录填写。

## 8. 计划评审记录

- 初次评审调查中断，未形成结论，不记 PASS。
- Round 1 独立聚焦评审：REVISE。H1 `accepted-high`：现有
  `__main__.py:134–169` 的 `receive_outer` 致命异常边界会把 CQ stale/digest 错误扩大为 run 退出；
  已在 §3.2 定义 CQ 专用类型化拒绝分支，保留旧路径与不可控故障边界。
- H2 `accepted-high`：现有 `runner.py:2784–2790` 通用 terminal 提示和
  `runner.py:6075–6080` 全 roster settle 条件与 CQ 多阶段等待不闭合；已在 §3.2 定义 CQ 阶段、
  同会话继续、host 最终 handoff 和恰好一次 terminal report，且不等待 Acceptance 才终态。
- Round 2 专项复审 PASS：H1/H2 已闭合，无剩余 Critical/High。实现、独立功能测试、L0/L1 均未执行。
- Round 3 独立复审（2026-09-08，应用户要求按设计规范复审）：REVISE，两项均经主 Agent 源码核实为
  `accepted-high`。H1：现有 run 级 T3 `run-fallback-timeout`（`runner.py:1843/4913/5683`，默认 5400
  秒累计 active，排除项仅 formal issue-pending）会在 CQ 审核/handoff 等待累计超时后 terminal latch
  并清理整个 run，与“等待审核是可恢复暂停”冲突；已在 §3.2 规定等待窗口纳入 T3 排除计时，不放宽
  T3 本身。H2：既有 scenario map 强制节 `cross_slice_competency_questions`（`scenario_map.py:284`、
  008B task `role_sources` 与 `scenario-map-six-sections-maintained` 终态证据）由生产 Coordinator
  维护且必含题干，011 未定义取值来源会架空隐藏盲测；已在 §3.3 规定该节只引用公开投影题或显式置空
  并记录覆盖缺口。随轮补齐：§3.4 public projection 目录 bind 机制、§3.3 题池不登记平台资源、
  §7 前置含 R3.0-009，测试计划新增对应断言（M6/M12/R1/I3、L0 前置）与 DC 前缀改名。修订后送
  Round 4 专项复审，仅复审本轮变更面。
- Round 4 专项复审（2026-09-08）：PASS，无剩余 Critical/High。H1 闭合：T3 排除可用 Runner 自有
  started/elapsed 对与 `_issue_pending_elapsed` 并联记账，两端均为 Runner 自有事件、可精确记账；
  不新增 `_latch_formal_candidate_failure` 调用点，时钟启动/drain 调用/默认 5400 秒均保留，等待
  窗口关闭后其他角色真实停滞只被延后计时而非抹掉。H2 闭合：`validate_scenario_map` 经真实执行
  验证“置空”与“引用公开投影题”两种取值均通过现有 validator，无需改动既有合同；public projection
  目录 bind 与 `runtimes/codex.py:4029-4060` 既有“预绑空目录、宿主后续写入可见”先例同构。
  次要记录（不构成发现，留实现/测试落实）：重叠等待窗口按区间去重并在 R1 补混合用例；CQ 显式
  等待访谈输入同样视为等待态；投影一致性外检放 Runner 侧比对（map 条目不得加溯源字段，
  `scenario_map.py:285` 三字段精确匹配）；置空覆盖缺口落到 acceptance batch 报告字段；实现阶段
  确认验收批次 LLM 调用在授权台账按“只读验收”口径留痕。实现、独立功能测试、L0/L1 均未执行。
