---
name: modeling-dev-loop
description: "Use when developing ontology-platform through real Modeling Team runs, supervising modeling progress, coordinating external Claude Code repairs, applying the per-authorization model schedule (cc-switch provider and Team model profile), or requesting another semantic-start budget. For the host delivery agent, not the isolated role authoring ontology payloads."
---

# 建模开发推进

执行此 Skill 的主智能体负责启动、观察、故障归因、开发协调、恢复和证据交接，持续推进用户的
原始建模目标。语义判断与候选内容归建模 Team；平台调用遵循选定 Profile 的 Protocol 边界。
Team 内部的 [ontology-modeling](../../modeling_team/skills/ontology-modeling/SKILL.md) 提供 Modeling 角色的
语义建模方法，各成员的技能对应关系见 [Team 技能目录](../../modeling_team/skills/README.md)。
Task、Profile 和角色提示补充执行合同。本 Skill 只提供宿主侧工作流，不加入生产角色的挂载输入。

## 开始或接续任务

1. 读取当前仓库 [AGENTS.md](../../AGENTS.md)，定位 [版本化需求](../../docs/requirements/)
   中本次目标及其交付记录。复用最近已验收的入口，不从历史方案重建 Team。
2. 在已有运行记录或本轮宿主工作目录写下：目标及验收阶段、获准材料、Task/Profile、运行环境、
   当前代码版本、已有 run 与写入状态、授权来源、已消耗/剩余 fresh starts、下一动作。
   接续时先读该记录、实际进程和事件，避免重复启动。用户中途补充要求不抹去原目标。
3. 复用会话已有授权。没有真实建模授权时，完成可独立开展的工作并申请；安装或调用本 Skill
   本身不授予 semantic start。每次授权默认三次 fresh starts，用户指定数量时以用户为准。
4. 获得新的建模次数授权时，先按 [授权时的模型调度](#授权时的模型调度) 取真实时间、判定
   高峰/非高峰并记录选定模型与 effort，再进入启动检查。
5. 按 [运行参考](references/team-runbook.md) 做安全启动所必需的最小检查。授权后通常须在
   20 分钟内开始第一次真实建模；超时即报告耗时来源并缩短通路，不能继续扩展预检。

## 授权时的模型调度

高峰与非高峰对应不同的模型档位，这是用户在授权时给出的约定；宿主的职责是如实判定、记录
并执行，不替用户重新定价，也不把该表说成已核实的官方价格。每次获得新的建模次数授权，先
调用当前时间工具取得真实时间并转换为 Asia/Shanghai 北京时间：周一至周五 09:00<=t<12:00
或 14:00<=t<18:00 为高峰；12:00、18:00 边界及周末为非高峰。把取时、时区、是否高峰、选定
模型/effort 和授权 ID 写入本轮宿主记录，后续启动、修复与交接按该记录核对。

- ClaudeCode（外部 Claude Code 开发/修复进程）：高峰经 cc-switch 把 provider 切至 glm，
  实际模型 `glm-5.3-flash`、effort `max`；非高峰且当前 provider 非 deepseek 时切回 deepseek，
  实际模型 `deepseek-flash`、effort `max`。目标 provider 已匹配时不做无意义切换，但仍
  核验 model/effort 与记录一致。主智能体自身是 Codex，不在 cc-switch 切换范围。
- Team：模型绑定写在 Team 独立 model-profile，不经 cc-switch。高峰 `glm-5.3-flash`、
  effort `max`，选用 profile `glm-flash-max`（经 `glm-direct` 路由；凭据只由宿主的
  loopback session 持有，角色不接触密钥）；非高峰 `deepseek-flash`、effort `max`，选用
  profile `deepseek-flash-max`。validate、baseline、run 及角色实际模型证据须与该选择一致。
- provider 用 `cc-switch -a claude provider list` 的当前标记现场发现（`provider current`
  原样输出带 API Key 片段，不直接原样输出或粘贴），不把机器特定 provider ID 写死；启动前
  清除会覆盖切换结果的旧 ambient `ANTHROPIC_MODEL`、`ANTHROPIC_BASE_URL` 等模型变量，只
  核验白名单字段，不打印密钥或整份 settings。命令与核验步骤见
  [运行参考](references/team-runbook.md)。
- 当前环境不支持所需模型/effort 时，如实反馈能力缺口并请用户决定，不悄悄替换成可用模型。
- 调度在授权时选定并适用整个 run：时间跨过时段边界不中断当前 run、不偷偷另开 start，
  也不给已冻结 run 更换模型；只有新一轮授权才重新判定。

## 保持观察和推进

通过可返回控制权的进程会话启动 Team，主智能体继续观察。默认每 30～60 秒读取新增事件，
立即处理错误、审核请求和阶段变化；根据当前工作调整频率，不把轮询次数或时间写成平台硬门。
长工具调用尽可能每 60 秒内返回一次控制权。Skill 不提供后台调度能力，会话结束后不能声称
仍在监控；必须交接真实进程、日志位置、待办与下一次观察责任。

每次观察（含周期巡检）先取一次真实时间（Asia/Shanghai）并写入观察/简报的开头，与证据
`recorded_at`（UTC）对齐核对，便于判断事件时点与滞后。观察比较：进程/工具活动、当前阶段、
最新有效产物或交接、待回答问题、第一阻塞点。
有效进展是问题得到回答、候选推进、交接完成、写入回执或检索证据增加；重复失败日志不是进展。
按可见证据检查获批范围、阶段及输入/写入边界，发现业务语义疑点交给建模 Team 澄清，
不要由宿主改写候选、指定本体拓扑或通过平台补造业务事实。

- **等待用户**：转交具体业务问题或 CQ 审核，保留等待状态；复用已确认答案。本次任务的用户
  授权明确允许依业务资料代答并补充资料时，按获准范围持续处理访谈与必要资料补充，不再反复
  询问同一权限；新增资料须标识为“授权新增业务定义/场景补充”并保留来源与修订，不得冒称
  原始证据、改写冻结源或据隐藏答案补料。超出获准范围的问题仍问用户；CQ 审批仍按本次具体
  授权，不暗自扩张；隐藏题隔离、授权额度与独立验收边界不变。设计自治不代替业务/CQ 审批。
  在项目测试中用户已授权宿主扮演业务方回答者时，宿主直接复用同一项目中有来源的既有确认，
  并把来源交给当前 run；不能从资料或既有确认支持的内容继续保留为未知，不为凑完整度编造答案。
- **仍有活动但较慢**：结合工具事件与阶段继续观察；几分钟无日志只能触发诊断，不能判死或重开。
- **重复错误、相互等待或已退出**：保留第一异常和相关事件，检查具体阻塞与写状态，再进入归因。
- **收到交付**：核对回执、阶段与产物，按当前验收阶段交给独立验收者；正常结束不是语义 PASS。

### CQ 生产交接必须由宿主显式完成

对 `competency_question_acceptance: true` 且
`acceptance_target: cq_semantic` 的任务，生产角色的 terminal 结果不会自动发布 CQ
交接。收到 Modeling、Protocol 和 Coordinator 的当前 run 结果后，宿主先用
`get_run_status`、`get_run_events` 和 `get_pending_actions` 核对角色已结束、没有待处理
issue、写入已排空且没有 unknown write；若已有 Runner 发布的 handoff，还要核对其
`ready=true`、`pending_writes=false`、`write_phase=read-only` 和 `unknown_writes=[]`。
同时只使用当前待办／事件给出的 `freeze_id`、`freeze_digest` 和可选 delivery binding，
不从旧记录重建绑定。

确认 readiness 后，宿主通过既有 Host 通道提交 `complete_cq_handoff`（Runner action
为 `cq_handoff_complete`）。核对返回成功、`acceptance_phase=acceptance_pending`、
当前 `acceptance_attempt_id` 和 `report_directory`；角色完成、提交被接受或 handoff
文件生成都不能单独当作语义验收完成。随后用当前 handoff 启动独立 `cq-acceptance`，
报告落盘后调用 `complete_cq_acceptance`，核对报告 digest、`cq_verdict` 和题目分母，
并保留 PASS、PARTIAL 或失败结果；交接或收口成功不等于 CQ PASS。具体绑定与收口步骤
见[运行参考的 CQ 交接与独立验收](references/team-runbook.md#cq-生产交接必须由宿主显式提交)。

## 阶段成果检查点（R3.0-015 S1+S2+S4）

启动前明确检查点开关与验收目标：默认 `r3-0-006-real-full` Task 未开启检查点，
验收目标为 `cq_semantic`；`r3-0-015-checkpoint-recovery` 开启检查点，但默认目标为
`full_joint`。按本轮获准范围选择或配置 Task，validate、baseline、run 使用同一文件；
不能为启用检查点而悄悄改变验收范围。具体见运行参考的“选择入口”。

启用 `modeling_checkpoints` 的 run 会在访谈成果落盘、CQ 冻结、每个 staged 回执和
production handoff 后自动保存阶段检查点；需要保存场景决定或已批准语义决定时由宿主
经 FIFO `action=checkpoint` 请求。Runner 只认磁盘上的实际已发布产物，角色自述“阶段
完成”而产物缺失得到的是可重试的类型化拒绝。判定以 `evidence/checkpoints.jsonl` 与
实际包为准。保存与检查不消耗 semantic start。

S2 起宿主可用 `checkpoint resume --mode production` 从一个已发布检查点跨进程续跑：
显式 checkpoint id 与全新 run id 必填，恢复时重新核对全部状态（全链写尾含检查点之后的
写入、平台 cursor 分页回读、业务审批来源通道）；对账未闭合得到的是带 `code`
的类型化拒绝（`source_active`、`write_unreconciled`、`scope_drift`、
`approval_binding_changed` 等），不会静默降级。续跑是一次新的语义开始（记账
`semantic_starts: 1`，平台侧无硬计数门），原 run 与其检查点只读不动；悬挂原写者按
stop channel 处理、单次等待 ≤60s；同一 root run 同机同时只允许一个续跑。手工清理
active 恢复前先核对 `recovery/` 引用。命令与消息格式见
[运行参考](references/team-runbook.md#生产续跑r30-015-s2)。

S4 起宿主可用 `checkpoint resume --mode acceptance` 对一个 COMPLETE
`production_handoff` 检查点做验收-only 续跑（S3 按设计延后，S4 不依赖 S3）：
`production_handoff` 只是把当前已验证状态和已知缺口交给独立验收，不是业务 Class，也不表示
未完成的值语义已自动完成或应挪到验收之后；正常阶段顺序仍由当前 Task/需求决定。
入口先做只读复核（沿用 S2 的 cursor 回读纪律：全链写尾闭合、原写者已停、冻结池按
快照摘要重校验、打包与已发布 handoff 一致），漂移得到类型化拒绝
（`acceptance_binding_changed` 等），绝不改模型或源 run。输入/输出分离：证据根
永远是原 run（旧 run_id、handoff 尝试字段与旧报告一字不动），新尝试、新报告与宿主
收尾记录只落新输出 run。已存在完整可用 PASS 报告（同批次同冻结摘要、全分母重算
通过）时只做核验与收尾（0 次模型会话）；否则经既有 cq-acceptance 执行/独立 Judge
路径重新执行，冻结的验收目标、题目分母与非盲状态不变，旧的 partial/fail 报告原样
保留、绝不拼接到新 PASS。记账 `semantic_starts: 0`。命令与边界见
[运行参考](references/team-runbook.md#验收续跑r30-015-s4)。

## 分清失败层与修改对象

| 失败层 | 证据特征 | 下一动作 |
| --- | --- | --- |
| `modeling-quality` | 业务理解、语义关系或源依据存在缺口 | 将具体发现交回建模 Team；必要时请用户澄清 |
| `platform-contract` | 合法请求被错误拒绝，读写、校验或授权实现偏离合同 | 派发 Claude Code 修复最窄实现层 |
| `collaboration/routing` | 消息丢失、交接错位、角色互等 | 核查路由与任务/提示合同，再反馈或委派修复 |
| `runtime/infrastructure` | 模型服务、进程、挂载、网络或本地依赖失效 | 对实际失败依赖做有界诊断和修复 |

证据不足时注明“尚未定位”并继续窄查，不强行归因。另记修改对象为 **实现 / prompt-contract /
流程设计**，不新增第五类失败：合同合理但代码未做到则修实现；合同未正确提供或有歧义则修
权威提示；各方遵守合同仍无法推进则审查流程设计。混合问题保留第一阻塞及后续因果关系。

某守卫阻断 run 时，先按 AGENTS.md 的 T0 依次检查必要不变量、硬拒绝代价、删除后果、Agent
可修复性及上层覆盖。风险已覆盖或后果可控时优先删除/降级为可恢复反馈；只有保护必要结果
才保留并收窄守卫。不能因一次缺字段、格式错误或可重试问题把整个目标永久终止。

## 自主设计与用户裁决

设计变动的大小本身不决定是否提问。符合 AGENTS.md 和用户授权，有具体证据支持收益，且对
相关语义、兼容性、权限、资源与验收影响有足够把握不会产生负面影响时，主智能体可自主决定，
包括较大的流程设计变化。记录“问题证据 → 变化 → 预期收益 → 影响判断与验证方式”，
更新归属需求/设计或权威提示面，再将具体开发任务交给 Claude Code。

不能仅凭“信心很高”绕过明确合同。会实质改变未经确认的业务含义/范围、破坏兼容性、削弱
授权/源忠实度/写入完整性/隐藏题隔离/独立验收，或存在关键影响未知时，先完成可独立进行的
分析，向用户提交可审阅的具体方案、证据、影响及对当前 run 的处置建议，等待相关决定。
需要变更 AGENTS.md 或扩展启动/费用/操作授权时同样由用户决定。用户在本次任务中明确授予的
访谈代答与资料补充授权按其获准范围执行，不外推为后续任务的默认授权。证据支持的常规变更
无需重复请示；修复不得顺带加入无当前需求的治理、审计、编排框架或产品功能。

## 委派修复并核验

使用 [Claude Code 修复交接](references/claude-repair.md) 提供明确的目标、范围、输入、证据、
权限、文件归属和完成标准。平台实现缺陷交外部 Agent 修复；流程设计问题由主智能体完成设计
判断，更新权威合同后再交其开发。仅需当前 Team 纠正输入时，通过既有反馈通道处理。

主智能体在修复期间继续观察 Team 与外部进程；同一文件有一个明确写入责任人，保留其他人的
改动。外部 Agent 发现范围变化或重大不确定性应及时返回；主智能体按上节裁决，避免逐层加审批。
核对实际 diff、原始失败的复测、仓库要求的测试及必要重启/端点检查，明确是否仍有未验证项。
只有文档/提示变动时执行相关合同/Skill 校验，不额外跑产品全套或重启。

## 恢复原目标

外部接口故障可通过当前 Team 的 `report_issue → pause → issue_resolution → resume` 保留
live Runner、原 Agent thread 和已完成产物。用户告知“接口已经修复完成，请继续”后，宿主
读取当前 active issue 的 run/reporter/epoch 和写入状态，按
[接口修复后继续同一 run](references/team-runbook.md#接口修复后继续同一-run) 发送绑定的
修复通知；已有授权内的同 run 续跑不重复申请授权。仅在已确认无写入且修复对当前进程生效时
复测原失败步骤；通知本身不是成功证据，也不能解除未知写入的关闭状态。

1. 若存在不确定写入，先查询实际 Batch、Attempt、资源及回执；明确落库状态前不重放 apply、
   删除资源或以 fresh start 掩盖现场。保留失败证据及资源归属。
2. 核实修复已进入实际运行环境：当前进程加载的代码、冻结 Task/Skill 和挂载不会随文件改动
   自动更新。`RUNNING` 状态或开发测试通过均不能证明原阻塞已解除。
3. 没有不确定写入、运行可接收反馈且修复已生效时，优先通过既有可恢复通道继续同一 start，
   观察原失败步骤的新结果。不能由宿主篡改冻结产物；外层 `action=resume` 只继续存活线程。
   原进程已退出且有有效检查点时，按上节 `checkpoint resume` 选择生产或验收接续；
   生产接续使用新 run/线程并消耗一次 fresh start，验收接续不消耗建模 start。
   仅有相同 run ID 不足以免计数：没有经当前合同证实、保留同一语义会话上下文的恢复机制时，
   重启建模 child 或另起建模 Agent 重做目标属于 fresh start。不能另起 Claude 会话替换
   Team 的 Modeling 角色后声称仍是原轮；外部 Claude 修复进程与建模子进程是不同职责。
4. 必须 fresh start 时先登记旧轮结果、修复版本、生效方式和安全清理/保留状态，再检查余额。
   更换 run ID 或模型会话不能规避计数；同 run 的安全续跑和机械修复不额外计 semantic start。
   prompt-contract 缺陷必须在下一次 start 前持久修复，不能只靠临时提醒。

## 额度、进展与收口

每轮终态及时用简洁中文说明进展、第一阻塞、修改和余额。分别记录语义建模及基础设施/修复、
评审、文档的有效时间；语义建模不足一半时暂停扩展平台/harness，报告原因并提出更短通路。

额度耗尽后停止新 start，继续完成已授权且安全的现场核查、窄修复与证据整理。按
[额度申请模板](references/progress-report.md) 先把本轮工作讲清楚，再提出具体额度申请；
新授权未到不能启动。若仍有不确定写入，先明确该阻塞，不能把追加额度当成恢复办法。

只按目标阶段判定结果，保留 `PARTIAL`、`REVISE` 或 `BLOCKED` 及缺失证据。最终语义验收者
不得创建、继续或修复被验收的 run，也不得改动其保留证据；参与过生产或修复则换新的验收者。
隐藏题经生产方知晓后只能作为已暴露的回归材料，不得追称盲测。L0 Runtime、L1 Modeling
quality、L2 Repeatability、L3 Productization 分开取证，后阶段不成为前阶段前置条件。
仅验收 L0 也不能跳过当前候选/写入所必需的业务确认；未知项按所选合同澄清或保留为明确未知，
不能因尚不验收 L1 而猜测并写入。L0 证据收口见运行参考，服务健康不是完整运行通过。
达到获准阶段且没有必要工作剩余时停止，交付结论、证据、相关提交、资源状态与后续缺口。
