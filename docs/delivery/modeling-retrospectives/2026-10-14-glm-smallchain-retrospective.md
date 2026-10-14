# 2026-10-14 GLM 小链建模复盘

本轮保持 **PARTIAL**。资产—故障—工单链已完成初建应用和三题公开反馈，第二轮只修改六条
关系的源结构证据，候选 r5 已审核但未应用。生产未交接，正式七题独立 Consumer／Judge
验收未启动。最后阻塞是供应商使用额度，不能据此判模型质量失败。

阶段反馈已经发生，仍有两类质量缺口：六条关系没有充分保留源非空／适用唯一性声明；
Consumer 对已返回的时间顺序和可空字段解释有遗漏。前者需要窄修模型，后者应纠正回答，
不能把全部公开反馈不足归为模型缺失。

## 范围、身份与证据

- session：`smallchain-glm-high-20261014-0657`；run：`r4009-20261014-glmhigh-smallchain-0657-start1`。
- 权威范围：[R4.0-009](../../requirements/requirements-v4.0.md#r40-009-多视角真实建模与独立语义验收)
  的有界小链；Task `r4-0-009-asset-fault-workorder`，Profile `r3-0-011-competency-question`。
  不涵盖全场景、SQL/API 映射、SLA、成本、库存采购或第二条链。
- 模型：实际基线八角色均为 `glm-direct / glm-5.3-flash / high`。启动 commit `0d0d575`；
  运行中工程修复 `922cf6f`、`ecb7495`。基线、源码修复和旧进程实际加载身份分别保留。
- Modeling 指令、Modeling skill、Task 当前 SHA256 均与 run baseline 完全相同；
  Coordinator 当前指令与 baseline 不同，后补 self-resume 提示不冒充初始加载版本。
- 题池 `cq-batch-0001 / freeze-0001`：7 题，3 公开、4 隐藏；freeze digest
  `74183671b21e0a089792cb274396846ae834de4f759a3fc0f17c526aca4a7cfd`。
  后续草稿落实原修改决定并重新审核，不改旧冻结、不缩小分母。本复盘未读取隐藏题／答案全文。
- 观察起点 2026-10-14 14:57:58 +08；结果／计时截止原保留摘要 17:14:51 +08。
  复盘时只读核对 `state.json` 仍为 WAITING_OWNER，两角色 provider waits 均 waiting，
  原 Runner PID 208093 仍存活。没有查询当前供应商额度，没有恢复或启动模型。
- 授权三轮：初建 1 轮；反馈后实际派发六关系修模再计 1 轮；已用 2、余 1。
  fresh semantic start 只有 1 次。r1—r4 同轮候选纠错、技术恢复、只读反馈不重复计次。

原件入口（本机 gitignored，保持只读）：

| 编号 | 原件 | 证明范围 |
| --- | --- | --- |
| E1 | [授权账本](../../../workspaces/v4-smallchain-glm-20261014-0657/authorization.json)、[保留摘要](../../../workspaces/v4-smallchain-glm-20261014-0657/latest-status.json) | 起点、两轮扣账、剩余额度、历史收尾及凭据撤销 |
| E2 | [run baseline](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/baseline-manifest.json)、[semantic-start](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/semantic-start.jsonl) | 实际角色／指令身份，真实 start |
| E3 | [staged-decisions](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/staged-decisions.jsonl)、[capability-calls](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/capability-calls.jsonl) | 引用执行、失败／成功 Attempt、版本与写入 |
| E4 | [Coordinator 事件](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/coordinator.jsonl)、[实际交接](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/deliveries.jsonl) | 候选审核、阶段公开交接、读窗口、修模派单 |
| E5 | [公开反馈](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/early-feedback/313e5311b45e436882abf9dd52cc4243/feedback.json)、[公开复核](../../../workspaces/delivery-sessions/smallchain-glm-high-20261014-0657/handoff-output/delivery/root-public-feedback-review.json) | 三份实际答案及治理返回、公开反馈资格；不是正式裁决 |
| E6 | [只读定位](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/runtime/coordinator/work/public-feedback-reconciliation.json) | 模型／回答缺口分层、关联自查、r5 六项修模目标 |
| E7 | [Delivery session 事件](../../../workspaces/delivery-sessions/smallchain-glm-high-20261014-0657/session-events.jsonl)、[工程修复记录](../../../workspaces/delivery-observation-repair-20261014/result.md) | 默认输入、线程关闭／接管、三处窄修复与开发验证 |
| E8 | [provider waits](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/provider-wait.jsonl)、[issue control](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/issue-control.jsonl)、[checkpoints](../../../workspaces/modeling-runs/r4009-20261014-glmhigh-smallchain-0657-start1/evidence/checkpoints.jsonl) | 恢复实际结算、额度阻塞、r5 保存；不证明未来恢复成功 |
| E9 | [用量差分报告](../../../workspaces/modeling-retrospective-glm-smallchain-20261014/usage-first-last-report/report.json)、[显式 scope](../../../workspaces/modeling-retrospective-glm-smallchain-20261014/usage-first-last-scope.json) | 七线程首／末累计差分的可复算部分用量；账单、全轮费用 unknown |

## 关联需求验证闭环

历史设计审阅、开发测试和独立功能证据仍按各原需求复用；本轮只追加实际覆盖和反证。
完整业务语义结果未取得，不能将局部采用改写为整体需求验证通过。

| 需求 | 本轮适用证据 | 本轮验证结论／缺口 |
| --- | --- | --- |
| R3.0-011／016 | 原七题冻结、实际 review 消费；MCP modified_question 对象合同工程修复；issue-1 有 resolution 和绑定 resume | 部分验证；Root 直调完成冻结不证明修后 MCP 原入口实测；self-resume 后仍靠技术说明解锁 |
| R4.0-009／007 | 同一 Ontology 两逻辑切片，49 候选项及6实际关系语句，revision3；未知保留 | 部分验证／PARTIAL；r5 未应用、正式7题未验收，不替代全场景 A1—A12 |
| R4.0-021；R4.3-001 | 启动1.31分钟、全链应用94.02分钟、保留窗口136.88分钟 | 部分验证；没有120分钟内完整独立PASS；有效语义工时及可扣故障并集 unknown |
| R4.3-002／003 | 9次引用执行调用；5次dry-run（1失败）、3次成功apply；另一次apply在写前租约拒绝 | 部分验证；引用执行实际采用，无成功写入重放；因版本推进而重做待执行批次dry-run合理，净收益未证 |
| R4.0-015；R4.3-004／015 | 首链后、生产终态前公开反馈；三题回答完整落盘，读窗口无漂移 | 本轮局部条件已验证，整体部分验证；Root启动操作，不能证明Delivery自主采用／净开销／最终质量 |
| R4.0-023；R4.3-005 | Delivery有三模型线程，后停止并由Root技术接管 | A13本轮自主交付条件验证未通过；历史A1—A12工程／独立功能结论保留；语义质量另判 |
| R4.0-024 | 49资源／245 statements完整治理扫描；36属性候选逐项处置、无悬空引用，有界生产自查PASS | 部分验证；属性定义的合理独立性不当缺陷，不新增强连通要求；生产自查不替代独立验收 |
| R4.3-006／007／017／018 | 公开反馈使用SPARQL／Ontology read model，保留响应及原引用 | 本轮未触发Context Query的缓存、自适应扩展与排序分支，既有结论保留，效果不关闭 |
| R4.3-010 | 公开题2 p21实际返回时间顺序、required/nullable、可空代码字段；答案未充分解释 | 本轮相关回答覆盖验证未通过；不是平台未返回或模型缺失，其他已通过项保留 |
| R4.3-013／014 | 候选、反馈引用实际可读；同run r5复用已有身份的指令已派发 | 部分验证；目录交接、净搬运收益、恢复三类场景与r5执行未齐全，未触发不判失败 |
| R4.3-016／019 | 台账优先、逐项定位并分层更新；现有用量工具生成七线程累计差分报告 | 部分验证；实际离线采用成立，独立功能／供应商对账、全轮用量仍未闭合 |
| R4.3-020 | 三Delivery线程实际有效窗口516800，生产四线程258400；Delivery共3次压缩 | 部分验证（Delivery实际配置采用）；没有同范围前后净成本或质量对照 |
| R4.3-022 | 正常用量事件错误唤醒有工程反例；修后新Delivery线程默认输入排除该类事件 | 原实现本轮无意义唤醒条件验证未通过；窄修后局部实际采用成立，净成本、独立工程及自主交付仍待证 |

## 已确认优化复核

沿[原台账](optimization-tracker.md)追加历史，不新增未经用户确认的优化项。

| 原编号 | 本轮效果 | 状态处理 |
| --- | --- | --- |
| ISSUE-V4-006 | 9次protocol_execute_approved_plans、8个Attempt proof绑定plan_ref／projection | 保持已关闭的引用采用范围；其他参数纠错不推翻此项 |
| R4.3-015 | 生产交接前取得三题公开反馈，窗口暂停／释放有原件；仍为Root操作 | 保持已实现待实测，追加局部成功；不关闭自主采用、最终质量和净开销预期 |
| RETRO-20261013-07／08 | 新指令实际加载；Coordinator纠正r1/r2已知结构遗漏，型号依赖进入模型；六关系源存在性仍漏 | **改为待调整**：改善成立但原遗漏防护仍未完全达到；r5候选补齐尚未应用，不能用计划关闭 |
| RETRO-20261013-09 | p21已返回必要限定但题2答案未充分表达，方向与业务未知局部正确 | **改为待调整**：有Consumer答案综合层的直接反证，不能继续仅写缺对照／待实测 |
| R4.3-013；RETRO-06 | 文件／反馈引用实际读取，关系计划使用已applied身份；中途错误可自修 | 保持待实测；实际接收成立，目录、更广路径和净返工效果未齐全 |
| R4.3-014；RETRO-03 | 无fresh生产恢复；r5已实质启动，不属于明确未启动repair owner清理 | 保持待实测；未覆盖三类恢复及旧未启动owner反例 |
| RETRO-01／02 | issue-1正式控制结算成立，但本人reporter提示不认识self-resume；CQ对象类型是另一合同缺陷 | 原范围保持待实测；不把新问题重记为旧修复未实现，不关闭旧provider-defer／可选序号预期 |
| RETRO-04／05 | 未触发旧缓存metadata或正式验收batch解析；公开反馈入口成功是不同路径 | 保持待实测；不据三题反馈关闭原分支 |
| RETRO-20261014-01 | 最后可识别rateLimitExceeded；不是原HTTP400／402错误纠正分支 | 保持待实测；不从同样“供应商故障”推导原修复效果 |
| R4.3-016 | 本次再次执行台账优先、原件归因、分层更新；未改旧裁决 | 保持已实现待实测，增加实际应用记录，不由作者自评独立效果PASS |
| R4.3-019／020／022 | 离线差分、实际窗口及噪声过滤的局部采用可定位 | 保持待实测／工程验证边界；未获得账单或净成本改善证据 |
| R4.3-021 | 未实施；3次压缩无真实compaction_response_id费用绑定 | 保持暂缓，不据压缩仍存在自动恢复设计或维护客户端补丁 |

## 时间、用量与质量

下表是阶段时点／跨度，不是有效语义工时。所有修模及技术纠错保留原起点；重叠不相加。

| 事件（2026-10-14，+08） | 从授权起点经过 | 含义 |
| --- | --- | --- |
| 14:57:58授权；14:59:16 semantic start | 1.31分钟 | 启动上限已满足，正式非空语义候选尚未开始 |
| 15:37:10七题冻结 | 39.21分钟 | 包括正常CQ拟题／审核、用户委托等待及技术阻塞；不全当浪费 |
| 15:46:21 Coordinator接受已核实self-resume | 48.39分钟 | issue控制15:30:00已记录，提示等待到此处约16分21秒；期间CQ仍并行 |
| 15:51:13首次实际语义候选核查 | 53.25分钟 | pre-freeze结构占位候选不算完整业务模型；该时点是最迟已观察到的非空候选 |
| 16:19:58首dry-run证明 | 82.00分钟 | 前有三次聚焦候选修订，机械合格不等于完整表达 |
| 16:25:15／16:25:27／16:31:59成功apply | 最后94.02分钟 | 三阶段，model revision0→1→2→3；从semantic start到全链92.71分钟 |
| 16:42:31公开反馈模型绑定；16:53:24已收到反馈 | 104.56／115.43分钟 | 后者是完成上界而非child精确结束；反馈晚于全链但早于正式交接 |
| 17:01:22第二轮实际派发；17:06:35 r5 dry-run派单 | 123.40／128.61分钟 | 六关系候选修订已开始并计第二轮；新执行仍未发生 |
| 17:07:09 Protocol额度wait；17:14:51收尾摘要 | 129.19／136.88分钟 | 两角色parked，r5待执行；不是完整PASS终点 |

有效语义／基础设施／文档工时及故障可扣并集 **unknown**，不据跨度计算语义占比或精确节省。
本次首链比此前DeepSeek小链更慢的表面数字，混合了题池、模型、范围和新工程变更，不能作为因果对照。

Delivery的391个唯一决策输入包分布为213／18／160；398次accepted分块投递不能当398次模型
请求。首线程213包含415条正常provider事件；修后15:38启动的新线程160包中此类事件为0。
这证明过滤实际采用，不能证明后续所有投递多余或断连全由噪声造成。Root 16:40:12接管记录
记载约30分钟受频繁steering影响；这是宿主观察，不冒充逐请求可复算故障扣时。

用量工具最初按逐响应／未证累计口径输出unknown，原报告保留。第二份scope对每个线程以
**第一份保留累计余额为非零基线**、最后余额作差，故不靠“目录看似fresh”假设零基线。
七线程已证差分输入78,229,470，命中75,318,592，未命中2,910,878，输出273,291（推理已包含）。
Delivery差分未命中1,741,532，占该七线程差分未命中59.83%；这是保留切口，**不是整轮比例或账单**。
首请求余额、公开反馈累计未证基线、外层Host／修复调用、无usage的失败请求未计入；供应商费用、
全轮吞吐及账单差额unknown。没有真实压缩response绑定，3次compacted不能直接估压缩费用。

## 已识别问题逐项定位

类别沿现有四层；“已定位”指原因和责任面有证据，不等于修复完成或独立验收。

| 问题／第一层 | 具体原因、证据及影响 | 修复／实际状态／下一动作 |
| --- | --- | --- |
| P1无意义Delivery唤醒；platform-contract | 019新增provider-attempts正常数值事件进入022的decision chain与模型输入；同一事件分类未覆盖该源，E7代码与先红后绿验证成立 | 922cf6f开发89项及Team2958通过；第三线程正常事件为0。局部真实采用成立，净费用和自主交付未证；不要削减必要错误／催办 |
| P2 CQ修改参数；platform-contract | Host/MCP标modified_question为str，Runner modify/supplement却要求完整问题对象；真实MCP反例5 failed→5 passed，E7 | ecb7495改dict及合法decision枚举；相关192项、Team2963通过。原run由Root直调完成冻结，修后MCP原步骤未实测，不把直调当MCP复测 |
| P3 issue-1标签代替task_id；collaboration/routing | 原外层指令仅有“作者提供的task_id”文字，无实际值，Protocol正确拒绝替代；E8 issue-report明确zero-mutation | 15:27:20给出快照真值，15:30:00正式guidance／resume，随后BuildSession创建。Task原已要求精确ID；是实际采用不足，不新增平台ID机制 |
| P4本人reporter恢复等待；collaboration/routing | Runner原有self_resumed已mark dispatch并RUNNING，不另发Runtime消息；旧Coordinator提示要求等第二消息，E4/E8及runner.py可核对 | 运行中技术说明15:46解锁；ecb7495持久纠正提示。旧线程消费临时指导成立，未来新线程加载持久修复效果未证 |
| P5 known结构遗漏与缺label；modeling-quality／platform-contract | r1仅11项，r2为44项仍漏资产状态／型号字段，r3为49项但7实体无source-grounded label。已加载authoring合同明确要求label | Coordinator聚焦审核补结构，Protocol拒绝无label后r4补齐。属于同轮候选修正，不多扣轮次；label防御保护语义命名且可修，T0无需删除或增加全面预审 |
| P6计划payload错误及早查coverage；platform-contract | entities dry-run的7项create_entity带非法description；失败回执invalid_command_payload，另在translation approval前查coverage得到approval_missing | 约53秒内新计划去非法字段并dry-run validated；后补正式批准。原工具允许自修，失败Attempt保留；后续只在原计划准备核对实际命令字段，无新增validator |
| P7 unlock空字段；platform-contract | skip-mode合同要求字段缺省，Agent写了空字段，unlock_skip_inconsistent返回可操作反馈 | 16:24修正后同run继续，E4/E3；保护真实解锁合同且可恢复，保持原窄校验，不升级永久run拒绝 |
| P8租约过期；platform-contract | BuildSession／lease先建立，候选审核期间lease过期，首apply写前被lease_expired拒绝；明确无写入 | 原身份重新取得lease后同批成功，E3；约17秒至成功回执，不是未知写入，不建议新恢复框架 |
| P9关系身份binding与摘要混用；platform-contract | p3-r1缺candidate引用，missing_candidate_reference；p3-r2后报告全计划canonical digest却被当raw-file digest | 加正确候选binding后dry-run；分别核算两种digest后同一计划成功apply，E3/E4。不是内容漂移／全量重审，沿现有交接命名区分摘要即可 |
| P10反馈引用offset；platform-contract | Coordinator第一次read_handoff_material用了非法byte offset，E4 16:53:41记载纠正 | 按工具参数重读完整正文后只读定位完成；一次低成本自修保留，不增加通用防御 |
| P11六关系源证据遗漏；modeling-quality | r4方向／文本关系存在，但value未明确源非空／适用唯一性；r4→r5仅6项改变，E6及原schema支持 | r5已审核，dry-run／apply／实际读回均未发生。RETRO-07／08待调整；不能把数据库物理约束升格为业务基数，独立质量仍待证 |
| P12答案综合遗漏；modeling-quality | 公开题2 p21实际包含required/nullable、源时间顺序及可空代码；答案只笼统说时间业务未知，E5。返回充分却未完整解释 | 已定位到Consumer表达层，高把握；RETRO-09待调整。最小纠正是回答前对照已返回的公开必答点及限定，不重复修已有时间属性、不增加检索深度 |
| P13供应商额度；runtime/infrastructure | 两角色rateLimitExceeded、每角色先流断连后terminal wait；上游报告五小时上限与19:59:12重置，未声明时区，E8 | 同run两wait保持waiting、issue-2确认无写入；不猜供应商内部原因，不把全部早期断连归于最终额度。仅外部可用后沿原wait恢复，本次未尝试 |

P1输入噪声已定位；“修后仍频繁steer→哪些必要变化可延后而不丢任务”的净因果**部分定位**：
已查三线程输入包、源码过滤、宿主接管及原生关闭证据，排除了“新线程仍复制正常provider
事件”解释。缺每个steer与实际未完成Host动作的唯一因果绑定，不能把后160包全部判冗余。
下一最小定位动作是在原有获准执行中对一个真实被打断CQ／Host操作核对其投递与完成链；
不建立新监控、删日志、全局停止观察或以猜测削减催办。

## 建议顺序与下次验证

1. **先完成已开始的第二轮。** 外部额度恢复后，核对原run／wait／issue-2和现存checkpoint，
   只将r5六关系差异编译、批准、dry-run/apply及受治理读回；同轮接续不再扣新轮。
   未变化的已成功资源不重放。若确实必须fresh生产start，再消耗余1轮。本次复盘不执行恢复。
2. **调整既有RETRO-09的回答采用。** 当前“已读字段＋笼统未知”→回答明确区分已声明结构、
   未确认业务含义和未取得证据，并在本次公开问题范围内核对必要限定。责任面为现有Consumer
   权威提示／回答步骤；这是未实施建议。验证用实际返回／答案对照；保持未知，不扩展Task。
   预期减少误判模型缺失和不必要修模，节省量unknown；若诱发补造业务事实则撤回最窄提示调整。
3. **保留022／020现有局部修复，先测完整交付。** 正常provider事件已从新线程排除，窗口已
   实际翻倍，无需再建设输入优化框架。后续验证Delivery是否自主完成实际Host动作、阶段
   衔接与完整交付，必要错误和待办不能被吞掉；用019完整口径观察费用，不保证过滤等额提速。

RETRO-07／08只加强原当前阶段审核的六关系源证据处置；r5已有候选，不重新创建建模能力或
逐字段台账。最有价值的下一证据是r5实际读回和原七题完整独立裁决，不是扩大平台或前置审计。
正式验收必须由未生产／修复该run的独立角色执行；本复盘不自任最终裁判、不把公开反馈当PASS。

## 本次记录变更与检查

更新v3.0的CQ／Host接口、v4.0的建模／自主交付／检查／计时边界，以及v4.3的本轮验证表。
台账追加本次旧项验证，07／08／09改待调整；未确认建议不新建优化编号。
仅报告与状态文档变更，未实施建议、修改运行原件、启动／恢复模型、查询额度或重启服务。
使用原工程测试证据；本次文档校验只证明链接、diff和证据绑定，不建立新语义验收结论。
新增本地链接／文件定位、Markdown围栏及表格列数、diff空白检查通过；r4／r5实际diff
恰为六关系、显式未知未变；用量比例按工具数值复算。全文件链接检查发现v4.0原有三个
前端旧路径已不存在，HEAD中相同引用也缺失；本次未修改这些无关历史链接。
