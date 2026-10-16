---
name: modeling-dev-loop
description: "Start, resume and actively supervise authorized OntoWeave modeling with independent Delivery or an existing manual Host workflow. Covers progress checks, blocker follow-through, repair handoff and evidence boundaries; not a production modeling or testing business-answerer skill."
---

# 建模开发推进

本 Skill 供技术宿主选择入口、交接配置、持续监看和接续已有任务。采用独立 Delivery 时，
Delivery 执行启动、流程控制、技术定位、宿主交接、恢复和证据交接；CQ 私有审核及平台代码／
配置修复由当前获准宿主沿既有 Host 入口承接，不由 Delivery 启动修复子 Agent。外层主智能体
仍负责主动观察实际建模进展、发现问题并跟踪处理结果。委派不解除监督责任。旧手动模式由外层
承担执行与监督。
语义判断与候选内容归建模 Team。当前统一图路径按 R4.3-024／025 由 Modeling 直接提交
变更意图，程序填充执行上下文并单次原子 apply；不经 Protocol 翻译／技术审批，不执行模型
 dry-run。成功后 Modeling 在获准范围内召回与节点展开自查，最终保留原关联检查及独立验收。
其他旧 Profile 保留其适用角色边界；历史 dry-run 证据不改写。索引失败不代表未写入，
不确定结果沿原 Batch／Attempt 身份对账；不以本次代码升级自动恢复暂停 run 或追加额度。
Team 内部的 [ontology-modeling](../../modeling_team/skills/ontology-modeling/SKILL.md) 提供 Modeling 角色的
语义建模方法，各成员的技能对应关系见 [Team 技能目录](../../modeling_team/skills/README.md)。
Task、Profile 和角色提示补充执行合同。本 Skill 只提供宿主侧工作流，不加入生产角色的挂载输入。

## 先选择交付模式（R4.0-023）

- 当前目标采用 [R4.0-023](../../docs/requirements/requirements-v4.0.md#r40-023-独立-delivery-agent-与统一用户交互)，
  或本轮已有 Delivery 配置／session 时，按[独立 Delivery 启动与接续](references/team-runbook.md#独立-delivery-启动与接续r40-023)
  准备获准配置、建立或接续 `modeling_team delivery` 会话。独立角色加载
  [delivery 技能](../../modeling_team/skills/delivery/SKILL.md)，通过受限 Host 工具推进全程。
  外层负责部署准备、业务输入转接和持续监督；通常通过 Delivery 推进启动、冻结、宿主交接与验收，
  主动检查其处理结果，不等待 Delivery 通知或用户询问才看进度。
  真实运行若需要外层技术补位，保留原因和实际动作，不能记为 Delivery 自主交付通过。
- 未采用独立 Delivery 的已有手动 run，或本轮明确选择旧手动入口时，保留原 run、授权、冻结和证据，按下文宿主流程
  接续；不为升级角色重新消费 start，也不把旧人工审核回填为 Delivery 自动审核。
- 测试代答者只接收获准业务资料、明确允许的测试补充和 Delivery 业务问题，必须使用独立
  会话与输入；不加载本 Skill，不继承技术宿主／Delivery 历史、Host 工具或私有目录。已经
  读取隐藏材料的监督会话不能切换身份充当代答者。回答可为未知，并保留测试来源。

下文“宿主／主智能体”指技术交付责任方，不指业务用户或测试代答者。旧手动模式由外层执行；
独立模式中流程控制归 Delivery，宿主保留私有 CQ 审核、平台修复和正式 issue 恢复责任。外层
持续核对进展、第一阻塞与下一动作，并协调必要的技术补位，不另建相互竞争的写入或修复链。
通用方法可复用，具体动作以 Delivery 已声明工具和 Host 私有入口为准，不把整份宿主手册注入
生产角色会话。

## R4.3-029 角色责任与宿主私有交接

在本需求路径中，Delivery 负责授权／轮次、阶段推进、流程阻塞、技术定位、交接、验收组织和
资源收尾。普通 Agent 消息、推理、工具成功、心跳和无决策变化的日志继续由程序保留而不持续
注入 Delivery；阶段、错误、未知写入、用户控制、报告资格、宿主待办和必要存活异常按既有
`delivery-decision-input/v1` 唤醒。Delivery 不读私有 CQ 题目、答案点、审核依据或 Judge 评分，
也不承担语义审核。

CQ 待审时，Delivery 通过现有 session 私有 journal 的 `request_host_action` 提交窄的
`kind="cq_review"` 请求；`bindings` 只携带当前待办的 `review_id`、`content_version`、
`content_digest`、`question_ids`，以及已有待办提供的 `phase`、`review_snapshot_ref`、
`draft_ref` 技术引用。run/session 与授权上下文来自 Delivery session，不复制题目。宿主在已有代审授权内读取快照并直接
调用 `submit_cq_review`，Delivery 仅核对真实审核回执、当前 digest、完整选题范围后调用
`freeze_cq`。宿主代审不取代独立 Consumer/Judge，冻结也不等于语义 PASS。

平台或运行缺陷由 Delivery 先按请求、参数、回执、版本、权限、写入状态和运行证据定位；确认
需要代码／配置修改、测试、部署或重启时，通过同一 journal 的 `request_host_action` 提交
`kind="platform_repair"`；若已有正式 issue，必须用真实 `issue_id`、`reporter_id`、
`control_epoch` 绑定当前 issue；尚未建 issue 的技术异常可用空 `bindings` 先交接，但不能走
正式 `resolve_issue`。再按需填写 `expected_behavior`、`actual_behavior`、`blocked_step`、`evidence_references`、
`checked`、`hypotheses`、`write_state`。宿主按 AGENTS 的 T0 复核并实施最窄授权修复，在同一 journal 追加
`host_action_result`（绑定 request、来源、`completed|blocked|failed`、结果引用和限制），并在
issue 路径直接用当前 `issue_id`、`reporter_id`、`control_epoch` 调用
`resolve_issue(resolution_type="repair_completed")`。Delivery 只观察真实 Host 回执和
issue-control 状态，再对账写入并恢复原步骤；request receipt、guidance、自然语言回复或工程
检查本身都不是修复完成。没有 Host 结果或验证原件时保持受影响步骤阻塞，不盲重放未知写入。

Coordinator 负责生产侧语义定位：使用 scenario-map、共享决定、候选／应用／治理读回引用和未决
项定位受影响的 slice／概念／关系，派原 Modeling 做局部查证；不默认全文重读、扩展源权限或
创建常驻诊断角色。它不是最终独立裁决者。失败仍限
`modeling-quality`、`platform-contract`、`collaboration/routing`、`runtime/infrastructure`；
证据不足写“尚未定位”并保留已查内容、竞争解释、缺口和下一步。隐藏反馈只传获准失败信号，
不得用隐藏题／答案／评分理由生成生产修模指导。

## 开始或接续任务

1. 读取当前仓库 [AGENTS.md](../../AGENTS.md)，定位 [版本化需求](../../docs/requirements/)
   中本次目标及其交付记录。复用最近已验收的入口，不从历史方案重建 Team。
2. 在已有运行记录或本轮宿主工作目录写下：目标及验收阶段、获准材料、Task/Profile、运行环境、
   当前代码版本、已有 run 与写入状态、授权来源、计数口径、
   已消耗/剩余建模轮次及独立的 fresh-start 数、下一动作。
   接续时先读该记录、实际进程和事件，避免重复启动。用户中途补充要求不抹去原目标。
3. 复用会话已有授权。没有真实建模授权时，完成可独立开展的工作并申请；安装或调用本 Skill
   本身不授予 semantic start。每次授权默认三次建模轮次；用户指定数量或明确仅按 fresh
   starts 计数时以用户为准。
   建模轮次与启动次数分开记录，按下节计数，不把同 run 内修模默认为免费。
4. 从已有台账读取最新适用用户指令；明确的执行者、模型、effort、service tier 和角色/范围
   优先于默认调度，接续或跨时段不使该选择失效。仅未指定部分按
   [运行参考的默认调度](references/team-runbook.md#授权时的模型调度) 选定并记录，不重复询问已确认选择。
5. 按 [运行参考](references/team-runbook.md) 做安全启动所必需的最小检查。每次授权后，除非
   用户明确允许更长准备期，须在 20 分钟内开始该授权后的第一次真实 semantic start；
   首次 start 若为 production checkpoint resume 也适用。后续恢复与只读验收记录实际耗时和
   阻塞，不从最初授权时点反复套用此期限或请求新授权；写入安全和 start 余额仍须核对。
   首次超时即报告耗时来源并缩短通路，不能继续扩展预检。

## 建模轮次计数与验收后修模

用户授权“建模次数”时，默认按建模轮次管理，而不是仅按 run 启动次数。沿用已有宿主台账，
不增加平台硬计数门；fresh semantic-start 仍作为独立运行事实保留。

- 初次实际开始语义建模计 1 次；启动前拒绝且未发生语义建模不扣次数。
- 初建中的连续分析、候选完善和分批写入属于同一轮。自查、评审或验收得到待修结果后，
  为修正语义定义、关系、范围或映射表达而实际开始一项新的实质修模任务，另计 1 次，
  即使复用同一 run、线程或 checkpoint。开始前核对余额并登记修模目标，实际开始时扣账。
- 同一修模任务为完成已登记目标发生的多个候选版本、dry-run、apply、格式纠错和删除指令
  修正不重复计次。任务交付后新的检查结果又要求实质修模，则开启下一轮；不能把持续返工
  全部并入初建，也不能把每次文件保存或 apply 当作新一轮。
- fresh production start、生产 checkpoint 接续或另起建模会话重做目标仍消耗 1 次；若它
  正是上述新修模轮的执行入口，只扣一次。安全同线程恢复且没有新的实质修模任务、平台／
  路由／凭据／格式修复及只读验收重试不扣建模轮次；供应商用量限额单独记录。

每轮记录轮次、目标、触发检查／验收、run/线程、候选与实际模型修订、开始证据、结果和
已用／剩余次数。不直接从候选版本数、模型 revision、apply 次数或 fresh-start 数推算余额。
旧台账只有启动计数时保留原值及原口径，按证据追加轮次校正；未能辨认的轮次写待核实，
不能宣称旧余额仍有效，也不能静默覆盖历史记录。

验收不通过时，保留原报告和完整分母，先依据已有逐点诊断定位最窄失败层：

- 已确认模型缺口或表达错误：还有授权且写入安全条件满足时，交建模 Team 开始下一轮
  修模并扣账，取得 dry-run/application 和实际读回后，交独立验收者再验收；不等用户重复
  说“继续”，也不为保留余额而反复做技术修复。只转交获准来源及可公开问题／诊断，不泄露
  隐藏题、答案或私有评分依据，不让验收者参与生产修模。
- 检索／Consumer／平台／运行故障：交当前指定修复者处理已证实的最窄层，恢复原失败步骤；
  未发生实质修模不扣建模轮次。`model-recall-insufficient` 本身不能证明模型缺失，原因
  未确定时记录待定位，不能凭裁决标签盲改模型，也不能把故障修复冒充修模轮次。

轮次耗尽、未知写入、缺少必要业务决定或真实外部阻塞时，明确停止受影响动作并交接；
保留可安全完成的只读核查。失败后汇报必须写明是否实际修模、扣了几次、再验收结果或
尚未修模的具体阻塞。保留原总耗时起点，分别记录语义、验收、技术修复和等待；只为当前
失败修最小必要差异，不持续扩展平台或 harness 来替代模型质量迭代。

派单／恢复时将当前轮目标、已用和剩余次数沿原Coordinator通道告知Modeling，并取得其
实际确认。剩余零允许已获准的当前初建继续分析／分批写入，但自查后纠正已应用关系的
端点仍是新的实质修模，即使原文字定义正确、仅更换引用也不算免费技术纠错。进入自查
时跟进原成员确认：缺口只报告保留，继续获准只读检查和资源收口，不自行“修好再交接”。
余额可用则由Delivery沿原授权确认并登记修模轮，无需重复申请用户授权；余额零则只读
交接，按现有控制待在途／未知写入结算后封存。指令accepted不等于成员确认或实际遵守，
不得仅凭后台存活或已发通知结束监督，也不新增平台次数硬门。

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
  宿主台账选定 Claude Code 修复执行者时读取 Claude CLI/provider 步骤；当前宿主自行修复
  沿用已有会话，独立模式按宿主私有交接处理，不为 Codex 子 Agent 切换 provider。
- 已安全写入的小链需要早期公开反馈：读[公开反馈（015）](references/team-runbook.md#已安全写入小链的早期公开反馈015)。
- 启动、接续或阶段范围变化：读[范围与入口核对（016）](references/team-runbook.md#启动接续范围与入口对账016)。
- Examiner、证据、Judge 或报告发生故障：读[故障交接（017）](references/team-runbook.md#examiner证据judge报告故障交接017)。
- 生产交接后选择当前 live 验收或 S4：读[下节交接分流](#cq-生产交接必须由宿主显式完成)，
  仅 S4 需要[同源停止与验收启动顺序](references/team-runbook.md#同源-checkpoint-只读验收启动)。

## 保持观察和推进

**监督随原目标持续，不随启动命令返回而结束。** 用户要求“开启建模”默认包含启动后的
进度核对、阻塞处理、修复后原步骤复测及适用的独立验收；用户明确只要求启动时才缩小范围。
先确定下一次如何拿到实际事件：当前会话主动读终端／状态，或已验证并实际接手的监督者。
后台终端、存活 PID、stdin 开放、Delivery 自带事件观察及“原团队保留”都不能代替外层监督，
也不会自行唤醒已结束的外层会话。没有可靠唤醒能力时，保持当前任务并用可返回控制权的
短等待继续读取；不要通过结束当前回合来等待后台事件。

两种模式都由外层主智能体保持当前任务并主动观察。独立模式同时保持 Delivery 进程和业务
输入通道，但进程存活或 Delivery 已接手不表示外层监督完成。默认每 30～60 秒读取新增
事件，立即处理错误、审核请求和阶段变化；根据当前工作调整频率，不把轮询次数或时间写成
平台硬门。长工具调用尽可能每 60 秒内返回一次控制权。不因启动成功、发布阶段报告或委派
修复就结束当前监督，也不等待用户再次说“继续”才检查。

每次观察核对实际进程／角色工具活动、最近有效产物、待答问题、第一阻塞和下一责任人。
发现问题后保留证据，向 Delivery 交接具体失败与处理目标，随后检查其动作、新回执和原失败
步骤是否恢复。发送通知、修复任务已启动或进程仍在运行都不是问题已解决。独立 Delivery 写入
`request_host_action` 后，宿主在同一 session 私有 journal 中读取新增待办及原 Host pending
actions，按授权处理并追加 `host_action_result`；没有后台常驻接单者时如实报告等待。Delivery
无法读取必要日志或执行获准操作时，外层在已有授权内补充最窄技术证据／动作并记录边界；平台
优化与实现修复仍交宿主／本轮指定执行者，不由监督者改写业务语义或扩展平台范围。

检查实际返回的完整性：展示文本可能在截断后仍能解析，不能据此判断字段缺失、清单为空
或操作完成。需要时核对原始事件／响应和哈希，提供角色已授权可读取的原结果；未核实前
保留缺口，不重构、拼接或补造内容，也不基于截断摘要下发推进建议。

用户要求定时检查时，使用当前环境真实可用的调度能力，按指定频率创建或复用任务；未指定
频率的定时检查可用每 15 分钟。核实下一触发时间、一次实际执行记录、检查／分析结果和后续
动作承接方。仅采集状态快照不等于分析推进。当前主动监督与定时检查共用已有待办，避免
重复发指令、重放写入或并发派修复。定时检查是补充，不代替当前任务中的持续观察。

定时检查启动时和准备执行推进动作前，都重新核对宿主负责的待办、最新监督记录以及实际
修复／运行进程；不能沿用检查开始时的状态判断。已有处理者时，本轮只读核查、分析和报告，
不另起修复或控制链。监督记录过期不等于处理者退出，先核实实际进程；发现重复进程时停止
重复执行者、保留其日志和已有改动，由原处理者对账后继续，不能直接覆盖共享文件。

Skill 本身不能建立后台任务，也不能保证唤醒当前宿主会话（Claude Code／Codex）。后台进程、
调度触发、独立分析进程和当前会话收到输入分别核实；不能把 systemd timer 成功说成当前会话已被唤醒。
没有实际调度能力时说明限制并保持当前任务观察，不声称已安排。获准结束或发生不可避免的
中断时交接真实进程、日志位置、待办、下一检查时间与处理责任；意外无人接手如实记监督空档。

监督空档是意外中断的事实记录，不是主动退出的许可。主动交接须核实接手者实际承接了
当前 run、待办和下一次检查；仅写“未安排接手”不能合理化结束监督。遇到需要用户决定的
外部阻塞时，先提出具体问题或可审阅的窄修复申请，说明等待期间的安全状态与恢复入口，
继续不依赖答案的工作。没有明确提出问题，不得把缺少 repair 配置／部署权限当成无限等待。
先核对已有授权；已获准时由宿主补齐配置，不重复索取确认。建模轮次余额不授予代码修复
或部署权限；已获准的窄修复按现有路径派发并持续核验，技术修复不额外消耗建模轮次。

观察记录沿用事件 `recorded_at`（UTC）或本次核实时间，显示时声明时区；不逐字段取时。
日常巡检只追加新增事件与待办，无实质变化不重填顶部摘要。观察比较：进程/工具活动、当前阶段、
最新有效产物或交接、待回答问题、第一阻塞点。
有效进展是问题得到回答、候选推进、交接完成、写入回执或检索证据增加；重复失败日志不是进展。
按可见证据检查获批范围、阶段及输入/写入边界，发现业务语义疑点交给建模 Team 澄清，
不要由宿主改写候选、指定本体拓扑或通过平台补造业务事实。

- **等待用户**：独立模式由 Delivery 提出业务问题；CQ 审核由获准宿主按下节私有 Host
  入口完成，Delivery 只核对绑定和回执；仅将业务歧义或范围变化交用户。旧手动模式按原授权
  转交业务问题或 CQ 审核。宿主直接代答仅限已有明确授权的旧手动模式；独立模式由真实用户
  或隔离的测试代答者提供业务输入。
  两种模式都可复用同一项目有来源、仍适用的既有确认；获准补充须标识为“授权新增业务定义/
  场景补充”并保留来源与修订，不冒称原始证据、不改冻结源、不据隐藏答案补料。资料不能
  支持的内容保留未知；超出获准范围的问题仍问用户，不反复请求已有授权。旧手动代答记录
  不作为独立 Delivery 的隔离证明；设计自治不代替业务/CQ 审批。
- **仍有活动但较慢**：结合工具事件与阶段继续观察；几分钟无日志只能触发诊断，不能判死或重开。
- **重复错误、相互等待或已退出**：保留第一异常和相关事件，检查具体阻塞与写状态，再进入归因。
- **收到交付**：核对回执、阶段与产物，按当前验收阶段交给独立验收者；正常结束不是语义 PASS。

### CQ 必答点审核与验收诊断（R4.0-013，R4.3-029覆盖）

CQ 逐点审核属于获准宿主的私有 Host 工作。独立 Delivery 不读取题目、答案点、来源依据或
审核理由，也不根据宿主自然语言重写审核意见；宿主直接沿当前 `review_id`、question、
content version/digest 调用 `submit_cq_review`，并在私有 note 记录授权、依据和逐点决定。
`panorama-draft`／`slice-draft` 不能批准或冻结，必须等待对应 review 阶段的当前快照。

Delivery 只从 `request_host_action(kind="cq_review")`、Host 审核回执和待办变化核对绑定、
完整选题范围和当前 digest，随后按既有顺序执行冻结。自查不等于批准，宿主代审不取代独立
Consumer/Judge；内容修订走现有决定与版本合同，不用 note 改冻结题，也不把私有理由传给生产角色。

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
  COMPLETE 的 `production_handoff` 检查点和安全资源保留。存活源用 `standby_run` 的新
  request receipt 核实写入排空、实际 key 撤回、模型修订与交接摘要；已退出源继续沿旧退出
  证据。随后在全新输出目录启动只读验收，不停止可信只读源、不释放生产 root lock。
  同 root acceptance 使用独立任务锁，上一任务报告和能力封口后即可继续下一批；保留的
  Consumer owner 不必退出。新报告由 Delivery 沿 `complete_cq_acceptance` 交回存活源。

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
先确认完整可用的交接检查点与安全资源保留；存活源须有本次可信只读封口回执，已退出源
沿原退出证据。入口继续只读复核（沿用 S2 cursor 回读纪律：全链写尾闭合、真实写能力
封口或原写者已停、冻结池按
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

独立模式由 Delivery 先用 `request_host_action(kind="platform_repair")` 把最小技术定位
交给当前获准宿主。Delivery 不再使用 `prepare_repair_task`、`start_repair` 或 `verify_repair`
启动新平台修复；这些历史操作只用于已在途任务的观察和收尾。宿主使用当前台账指定的修复
执行者，在 AGENTS T0 复核后完成窄代码／配置修复、测试、部署或重启，并通过既有 Host
`resolve_issue(repair_completed)` 提交正式恢复；配置与证据边界见
[接口修复后继续同一 run](references/team-runbook.md#接口修复后继续同一-run)。

交接材料提供明确的目标、范围、输入、证据、权限、文件归属和完成标准，不包含隐藏题、答案、
私有评分或凭据。宿主在同一 session journal 追加 `host_action_result`，绑定原请求、来源、
状态和结果限制；Delivery 与外层只据真实回执、验证原件和 issue-control 状态判断下一步。
流程设计问题由主智能体更新权威合同后再交开发；仅需当前 Team 纠正输入时，通过既有反馈通道处理。

主智能体在修复期间继续观察 Team 与外部进程；同一文件有一个明确写入责任人，保留其他人的
改动。外部 Agent 发现范围变化或重大不确定性应及时返回；主智能体按上节裁决，避免逐层加审批。
核对实际 diff、原始失败的复测、仓库要求的测试及必要重启/端点检查，明确是否仍有未验证项。
只有文档/提示变动时执行相关合同/Skill 校验，不额外跑产品全套或重启。

## 恢复原目标

外部接口故障可通过当前 Team 的 `report_issue → pause → issue_resolution → resume` 保留
live Runner、原 Agent thread 和已完成产物。宿主收到 Delivery 的平台修复请求后，读取当前
active issue 的 run/reporter/epoch 和写入状态；完成 T0、修复、测试和必要部署／重启后，按
[接口修复后继续同一 run](references/team-runbook.md#接口修复后继续同一-run) 直接提交绑定的
`resolve_issue(repair_completed)`，并在 session journal 追加 `host_action_result`。已有授权内
的同 run 续跑不重复申请授权。仅在已确认无写入且修复对当前进程生效时复测原失败步骤；Host
回执或通知本身不是成功证据，也不能解除未知写入的关闭状态。

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
   更换 run ID 或模型会话不能规避计数；同 run 的安全续跑和机械修复不额外计 semantic start；
   若启动实质修模，仍按建模轮次扣账。
   prompt-contract 缺陷必须在下一次 start 前持久修复，不能只靠临时提醒。

## 额度、进展与收口

阶段变化、新阻塞、配置/授权变化或接续交接时，在已有记录顶部更新[最新摘要](references/progress-report.md#最新摘要r40-021)，
列 `completed/remaining/next/authorization/wait/resource/handoff`。仍有授权内明确待办且条件
满足时，汇报后继续：live 验收保持源 Runner 存活；S4 以安全 checkpoint、可信只读封口
（或原退出证据）进入新目录验收。任务封口后继续另一获准批次；隐藏完成且公开仍待办也继续，
不等待用户反复说“继续”。缺业务定义、权限、兼容性决定或新建模轮次额度时，只等待受影响
动作，完成独立可做项；不扩权、不把余额当必须耗尽的目标。

只有原获准目标完成、用户暂停/取消、到期或无安全可继续动作时才收尾。结束进程的临时密钥
及时撤销；连续任务资源按已有生命周期保留，已撤销密钥不复活，必要重新准备记录真实时点
及授权。监督必须结束时交接 run/process/checkpoint、待办、余额和下一观察责任；未安排
接手则如实写未安排，不声称存在后台监控。细节见[阶段继续与收尾](references/team-runbook.md#阶段继续等待与收尾r40-020)。

发送结束当前回合的 final 前，核对：原目标与适用验收是否完成；未完成时，是否已有用户的
暂停／取消／到期要求、已实际承接的交接，或确实只能等待且已向用户明确提出所需决定／
外部操作。启动成功、阶段报告、修复任务已派发、`finish_delivery` 返回 PARTIAL 或原成员
仍存活均不是结束条件。`WAITING_REPAIR` 仍有诊断、申请、派修、验证或恢复待办时，先处理
该待办；不要把“已启动＋余额＋保留后台进程”作为整项任务的最终交付。

用户短进度说明实际成果、第一阻塞与下一动作，详细字段保留在运行记录；无变化不重复全表。
每轮终态及时用简洁中文说明进展、第一阻塞、修改和余额。分别记录语义建模及基础设施/修复、
评审、文档的有效时间；语义建模不足一半时暂停扩展平台/harness，报告原因并提出更短通路。
按[分类计时](references/progress-report.md#分类耗时r40-021) 区分生产语义、独立消费、等待、
修复测试、评审文档、启动清理；UTC 区间保留来源及 unknown/estimate，墙钟按 union，累计
Agent 时间另列，不能把进程存活或重叠分类相加当有效语义时间，也不把局部比例外推全 session。

额度耗尽后停止新的建模启动和实质修模，继续完成已授权且安全的现场核查、窄修复与证据整理。按
[额度申请模板](references/progress-report.md) 先把本轮工作讲清楚，再提出具体额度申请；
新授权未到不能启动。若仍有不确定写入，先明确该阻塞，不能把追加额度当成恢复办法。

只按目标阶段判定结果，保留 `PARTIAL`、`REVISE` 或 `BLOCKED` 及缺失证据。最终语义验收者
不得创建、继续或修复被验收的 run，也不得改动其保留证据；参与过生产或修复则换新的验收者。
隐藏题经生产方知晓后只能作为已暴露的回归材料，不得追称盲测。L0 Runtime、L1 Modeling
quality、L2 Repeatability、L3 Productization 分开取证，后阶段不成为前阶段前置条件。
仅验收 L0 也不能跳过当前候选/写入所必需的业务确认；未知项按所选合同澄清或保留为明确未知，
不能因尚不验收 L1 而猜测并写入。L0 证据收口见运行参考，服务健康不是完整运行通过。
达到获准阶段且没有必要工作剩余时停止，交付结论、证据、相关提交、资源状态与后续缺口。


## 原 Team 待命与统一会话（R4.0-028 / R4.2-008）

正常业务完成及认可保留原 Delivery、常驻 Team 与已经启动的 Consumer，不预建尚未启动
Consumer。通过 `standby_run` 核实只读封口，`consult_team` 沿原 Coordinator/Team 追问；
结论、freeze、回答与 Judge 报告不改。暂停/继续是发给当前 Coordinator 或实际 Consumer/
Judge 的消息，由 Agent 自行等待/恢复，Delivery 依据真实确认展示 pending/effective，
不置全局执行开关、不强制 interrupt、不把等待 turn 当任务完成。授权到期和撤回独立。
stdin EOF、网页关闭、轮询和余额到期不等于显式 stop。明确 stop 才按绑定归属停止原
owner、核对实际线程/进程退出与资源清理，最后停止 Delivery；未知清理如实保留 partial。
网页与 CLI 只连接已有 Delivery 的本机入口，保持 original message_id/source/question
reference；离线只读，不自动唤醒或重放 unknown 消息，业务结果与投递回执分开。
