---
name: modeling-dev-loop
description: "Start or resume an authorized ontology-platform modeling delivery: hand R4.0-023 lifecycle work to the independent Delivery session, or continue an existing manual Host workflow. Covers configuration, supervision, repair handoff and evidence boundaries; not a production modeling or testing business-answerer skill."
---

# 建模开发推进

本 Skill 供技术宿主选择入口、交接配置和接续已有任务。采用独立 Delivery 时，由 Delivery
负责启动、观察、故障归因、修复协调、恢复和证据交接；旧手动模式仍由外层主智能体承担这些
职责。语义判断与候选内容归建模 Team；平台调用遵循选定 Profile 的 Protocol 边界。
Team 内部的 [ontology-modeling](../../modeling_team/skills/ontology-modeling/SKILL.md) 提供 Modeling 角色的
语义建模方法，各成员的技能对应关系见 [Team 技能目录](../../modeling_team/skills/README.md)。
Task、Profile 和角色提示补充执行合同。本 Skill 只提供宿主侧工作流，不加入生产角色的挂载输入。

## 先选择交付模式（R4.0-023）

- 当前目标采用 [R4.0-023](../../docs/requirements/requirements-v4.0.md#r40-023-独立-delivery-agent-与统一用户交互)，
  或本轮已有 Delivery 配置／session 时，按[独立 Delivery 启动与接续](references/team-runbook.md#独立-delivery-启动与接续r40-023)
  准备获准配置、建立或接续 `modeling_team delivery` 会话。独立角色加载
  [delivery 技能](../../modeling_team/skills/delivery/SKILL.md)，通过受限 Host 工具推进全程。
  外层负责部署准备和业务输入转接，不再手动替它启动生产、冻结 CQ、派修复或切换验收。
  真实运行若需要外层技术补位，保留原因和实际动作，不能记为 Delivery 自主交付通过。
- 未采用独立 Delivery 的已有手动 run，或本轮明确选择旧手动入口时，保留原 run、授权、冻结和证据，按下文宿主流程
  接续；不为升级角色重新消费 start，也不把旧人工审核回填为 Delivery 自动审核。
- 测试代答者只接收获准业务资料、明确允许的测试补充和 Delivery 业务问题，必须使用独立
  会话与输入；不加载本 Skill，不继承技术宿主／Delivery 历史、Host 工具或私有目录。已经
  读取隐藏材料的监督会话不能切换身份充当代答者。回答可为未知，并保留测试来源。

下文“宿主／主智能体”指技术交付责任方，不指业务用户或测试代答者。旧手动模式由外层执行；
独立模式中相应职责归 Delivery，外层只核对交接是否到位，不另建第二条推进链。通用方法可
复用，具体动作以 Delivery 已声明工具为准，不把整份宿主手册注入其会话。

## 开始或接续任务

1. 读取当前仓库 [AGENTS.md](../../AGENTS.md)，定位 [版本化需求](../../docs/requirements/)
   中本次目标及其交付记录。复用最近已验收的入口，不从历史方案重建 Team。
2. 在已有运行记录或本轮宿主工作目录写下：目标及验收阶段、获准材料、Task/Profile、运行环境、
   当前代码版本、已有 run 与写入状态、授权来源、已消耗/剩余 fresh starts、下一动作。
   接续时先读该记录、实际进程和事件，避免重复启动。用户中途补充要求不抹去原目标。
3. 复用会话已有授权。没有真实建模授权时，完成可独立开展的工作并申请；安装或调用本 Skill
   本身不授予 semantic start。每次授权默认三次 fresh starts，用户指定数量时以用户为准。
4. 从已有台账读取最新适用用户指令；明确的执行者、模型、effort、service tier 和角色/范围
   优先于默认调度，接续或跨时段不使该选择失效。仅未指定部分按
   [运行参考的默认调度](references/team-runbook.md#授权时的模型调度) 选定并记录，不重复询问已确认选择。
5. 按 [运行参考](references/team-runbook.md) 做安全启动所必需的最小检查。每次授权后，除非
   用户明确允许更长准备期，须在 20 分钟内开始该授权后的第一次真实 semantic start；
   首次 start 若为 production checkpoint resume 也适用。后续恢复与只读验收记录实际耗时和
   阻塞，不从最初授权时点反复套用此期限或请求新授权；写入安全和 start 余额仍须核对。
   首次超时即报告耗时来源并缩短通路，不能继续扩展预检。

## 授权时的模型调度

最新适用用户指令优先，未指定部分沿用[运行参考的默认调度](references/team-runbook.md#授权时的模型调度)。
接续与跨时段不重选已确认配置，不为统一显示重开 start；详细传递与核对按需读运行参考。

## 按需导航

入口先按当前版本需求和获准 Task 定位，不把历史 v3 入口当通用默认。现成 v4 Task 为
[r4-0-009-multiview-semantic-acceptance.yaml](../../modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml)，
其适用范围、检查点和验收目标仍以本轮授权为准；选择入口见[运行参考](references/team-runbook.md#选择入口)。

- 配置与授权变化：先核对 session 台账的执行者、model/profile、effort、service tier 和适用范围，
  请求、启动传递和实际生效分开记录，无法核实写 `unverified`，不支持写 `unsupported`。
  用户未覆盖的[默认调度](references/team-runbook.md#授权时的模型调度)及
  [配置传递](references/team-runbook.md#session-配置传递与核对r40-019)按需读取；
  仅旧手动模式选定 Claude Code 修复者时读取 Claude CLI/provider 步骤，独立模式按配置使用
  受限修复工具，不为 Codex 子 Agent 切换 provider。
- 已安全写入的小链需要早期公开反馈：读[公开反馈（015）](references/team-runbook.md#已安全写入小链的早期公开反馈015)。
- 启动、接续或阶段范围变化：读[范围与入口核对（016）](references/team-runbook.md#启动接续范围与入口对账016)。
- Examiner、证据、Judge 或报告发生故障：读[故障交接（017）](references/team-runbook.md#examiner证据judge报告故障交接017)。
- 生产交接后选择当前 live 验收或 S4：读[下节交接分流](#cq-生产交接必须由宿主显式完成)，
  仅 S4 需要[同源停止与验收启动顺序](references/team-runbook.md#同源-checkpoint-只读验收启动)。

## 保持观察和推进

旧手动模式通过可返回控制权的进程会话启动 Team，由主智能体继续观察；独立模式保持 Delivery
进程和业务输入通道，由 Delivery 观察 Team。默认每 30～60 秒读取新增事件，
立即处理错误、审核请求和阶段变化；根据当前工作调整频率，不把轮询次数或时间写成平台硬门。
长工具调用尽可能每 60 秒内返回一次控制权。Skill 不提供后台调度能力，会话结束后不能声称
仍在监控；必须交接真实进程、日志位置、待办与下一次观察责任。

观察记录沿用事件 `recorded_at`（UTC）或本次核实时间，显示时声明时区；不逐字段取时。
日常巡检只追加新增事件与待办，无实质变化不重填顶部摘要。观察比较：进程/工具活动、当前阶段、
最新有效产物或交接、待回答问题、第一阻塞点。
有效进展是问题得到回答、候选推进、交接完成、写入回执或检索证据增加；重复失败日志不是进展。
按可见证据检查获批范围、阶段及输入/写入边界，发现业务语义疑点交给建模 Team 澄清，
不要由宿主改写候选、指定本体拓扑或通过平台补造业务事实。

- **等待用户**：独立模式由 Delivery 提出业务问题；已有委托的 CQ 审核由 Delivery 按下节
  完成，仅将业务歧义或范围变化交用户。旧手动模式按原授权转交业务问题或 CQ 审核。
  宿主直接代答仅限已有明确授权的旧手动模式；独立模式由真实用户或隔离的测试代答者提供业务输入。
  两种模式都可复用同一项目有来源、仍适用的既有确认；获准补充须标识为“授权新增业务定义/
  场景补充”并保留来源与修订，不冒称原始证据、不改冻结源、不据隐藏答案补料。资料不能
  支持的内容保留未知；超出获准范围的问题仍问用户，不反复请求已有授权。旧手动代答记录
  不作为独立 Delivery 的隔离证明；设计自治不代替业务/CQ 审批。
- **仍有活动但较慢**：结合工具事件与阶段继续观察；几分钟无日志只能触发诊断，不能判死或重开。
- **重复错误、相互等待或已退出**：保留第一异常和相关事件，检查具体阻塞与写状态，再进入归因。
- **收到交付**：核对回执、阶段与产物，按当前验收阶段交给独立验收者；正常结束不是语义 PASS。

### CQ 必答点审核与验收诊断（R4.0-013）

独立模式由 Delivery 依据 R4.0-023 的已记录委托组织审核，在 note 中注明 Agent 代审、授权
和资料／题目版本；依据充分且范围内的题目不再逐项请用户批准，旧人工记录保持原样。

生成后、冻结前，按[运行参考](references/team-runbook.md#cq-必答点审核与验收诊断r40-013)
在现有审核中复核公开／隐藏题的每个必答点，将获准依据、题意对应及保留／修改／移出理由
写入 `submit_cq_review.note`。自查不等于批准，代审只使用已有明确授权；内容修订走现有
决定与版本合同，不用 note 改冻结题，也不把私有理由传给生产角色。

交付验收报告时分别说明端到端结果、逐点诊断和覆盖缺口。`model-recall-insufficient`／
`modeling-quality` 只表示端到端语义消费未满足，不能据其数量推导模型缺失率或知识覆盖率。
复用已有响应、读取复核和漂移记录，按运行参考核对本题及旁证的诊断资格；不通过时保留
Judge 原 note／verdict，说明“证据资格未通过，有效归因：原因未确定”，不新增诊断查询。

### 场景地图进度同步（R4.0-014）

候选交接、相关修订、计划保存／交接前及生产恢复后，由 Coordinator 核对实际候选并更新
地图；Modeling 通过已有消息给出切片／视角、候选版本／关键 item、已表达范围、待办／未知
和下一步。最终同步在 Coordinator 生产 terminal 之前完成，再沿既有写入排空与 handoff
摘要绑定顺序交接。宿主核对地图能定位成果和缺口，不要求七视角或全 modeled。

modeled 只是当前已有表达，可为部分范围，不代替业务 confirmed、平台回执或独立验收。
计划保存先尽量同步已到达更新；紧急保存／到期停止保留实际内容，注明待核对项，不等待地图
完美。恢复先核对包、scope／identity_mapping、写入状态及真实候选，再由 Coordinator 更新
生产工作副本并接续；pending 不表示未写入，确定成功不重复 apply，不确定写入按原机制核实。
fork 保留中立候选进展，旧回执只属源记录，新计划按新 scope／身份映射核对。

handoff 绑定后发现普通过期，仅在宿主交付说明中记录差异、实际候选定位与后续待办，不覆盖
原图、旧 checkpoint／报告或摘要，不进入 Judge 业务证据。验收-only 恢复保持源图只读；后续
获准恢复生产才更新可写副本。实际摘要漂移仍沿既有校验报告，不以修进度豁免。详细步骤见
[运行参考](references/team-runbook.md#场景地图进度交接保存与恢复r40-014)。

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
文件生成都不能单独当作语义验收完成。生产角色 terminal、handoff ready 和 managed process
退出分别核对，再按实际入口分流：

- **live `cq-acceptance`**：源 Runner 保持存活，生产静默、写入已排空，用当前 handoff 启动
  独立验收。报告落盘后向存活源 run 调用 `complete_cq_acceptance`，核对报告 digest、
  `cq_verdict` 和完整题目分母；不要为“生产已完成”提前 stop。
- **S4 checkpoint acceptance continuation**：先用 `inspect_checkpoints` 确认显式、有效且
  COMPLETE 的 `production_handoff` 检查点和所需资源可安全保留，再经 stop/receipt/managed
  exit 释放源 writer，随后复核绑定并在全新输出目录启动只读验收。不要先 stop 后才发现
  没有可用检查点，也不向已死源 FIFO 投递验收收口消息。同 root 的公开/隐藏 continuation
  等前一托管进程退出，顺序由获准任务安排。

unknown write 先对账，不能靠停止或删锁掩盖。两条路径均保留 PASS、PARTIAL 或失败结果；
交接或收口成功不等于 CQ PASS。具体绑定与收口步骤见
[运行参考的 CQ 交接与独立验收](references/team-runbook.md#cq-生产交接必须由宿主显式提交)。

## 阶段成果检查点（R3.0-015 S1+S2+S4）

启动前按当前版本需求、Task 和授权明确检查点开关与验收目标，validate、baseline、run
使用同一文件；不能为启用检查点而悄悄改变验收范围。现成 v4 Task 已开启检查点并使用
`cq_semantic`；历史 v3 Task 的区别按需见[选择入口](references/team-runbook.md#选择入口)。

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
先确认完整可用的交接检查点与安全资源保留，再停止源 writer 并确认退出；入口继续做只读
复核（沿用 S2 的 cursor 回读纪律：全链写尾闭合、原写者已停、冻结池按
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
| `modeling-quality` | 建模或端到端语义消费未满足；单凭 CQ 粗粒度字段不能证明模型缺失 | 按逐点证据区分模型、检索、Consumer 和原因未确定，再交对应环节 |
| `platform-contract` | 合法请求被错误拒绝，读写、校验或授权实现偏离合同 | 派发当前台账指定的修复 Agent 修复最窄实现层 |
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
更新归属需求/设计或权威提示面，再将具体开发任务交给当前台账指定的修复 Agent。

不能仅凭“信心很高”绕过明确合同。会实质改变未经确认的业务含义/范围、破坏兼容性、削弱
授权/源忠实度/写入完整性/隐藏题隔离/独立验收，或存在关键影响未知时，先完成可独立进行的
分析，向用户提交可审阅的具体方案、证据、影响及对当前 run 的处置建议，等待相关决定。
需要变更 AGENTS.md 或扩展启动/费用/操作授权时同样由用户决定。用户在本次任务中明确授予的
访谈代答与资料补充授权按其获准范围执行，不外推为后续任务的默认授权。证据支持的常规变更
无需重复请示；修复不得顺带加入无当前需求的治理、审计、编排框架或产品功能。

## 委派修复并核验

独立模式由 Delivery 使用 `prepare_repair_task → start_repair → get_repair_status`，再经
`verify_repair → get_repair_verification_status` 核验生效后恢复原步骤；配置与工具边界见
[独立 Delivery 修复](references/claude-repair.md#独立-delivery-模式r40-023)。下述外层派发方式仅用于旧手动模式。

使用 [当前台账指定修复 Agent 的交接](references/claude-repair.md) 提供明确的目标、范围、输入、证据、
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
   重启建模 child 或另起建模 Agent 重做目标属于 fresh start。不能另起修复 Agent 会话替换
   Team 的 Modeling 角色后声称仍是原轮；修复进程与建模子进程是不同职责。
4. 必须 fresh start 时先登记旧轮结果、修复版本、生效方式和安全清理/保留状态，再检查余额。
   更换 run ID 或模型会话不能规避计数；同 run 的安全续跑和机械修复不额外计 semantic start。
   prompt-contract 缺陷必须在下一次 start 前持久修复，不能只靠临时提醒。

## 额度、进展与收口

阶段变化、新阻塞、配置/授权变化或接续交接时，在已有记录顶部更新[最新摘要](references/progress-report.md#最新摘要r40-021)，
列 `completed/remaining/next/authorization/wait/resource/handoff`。仍有授权内明确待办且条件
满足时，汇报后继续：live 验收保持源 Runner 存活，S4 按安全 checkpoint→stop/exit→新目录
验收切换；隐藏完成且公开仍待办也继续，
不等待用户反复说“继续”。缺业务定义、权限、兼容性决定或新 start 额度时，只等待受影响
动作，完成独立可做项；不扩权、不把余额当必须耗尽的目标。

只有原获准目标完成、用户暂停/取消、到期或无安全可继续动作时才收尾。结束进程的临时密钥
及时撤销；连续任务资源按已有生命周期保留，已撤销密钥不复活，必要重新准备记录真实时点
及授权。监督必须结束时交接 run/process/checkpoint、待办、余额和下一观察责任；未安排
接手则如实写未安排，不声称存在后台监控。细节见[阶段继续与收尾](references/team-runbook.md#阶段继续等待与收尾r40-020)。

用户短进度说明实际成果、第一阻塞与下一动作，详细字段保留在运行记录；无变化不重复全表。
每轮终态及时用简洁中文说明进展、第一阻塞、修改和余额。分别记录语义建模及基础设施/修复、
评审、文档的有效时间；语义建模不足一半时暂停扩展平台/harness，报告原因并提出更短通路。
按[分类计时](references/progress-report.md#分类耗时r40-021) 区分生产语义、独立消费、等待、
修复测试、评审文档、启动清理；UTC 区间保留来源及 unknown/estimate，墙钟按 union，累计
Agent 时间另列，不能把进程存活或重叠分类相加当有效语义时间，也不把局部比例外推全 session。

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
